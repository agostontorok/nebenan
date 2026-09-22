import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "./style.css";
import { eventPatch, berlinInput } from "./event-patch.mjs";
import { berlinDay, dateRange, filterEvents } from "./filters.mjs";
import { shouldFitInitialMap, MAX_DRIFT_ZOOM } from "./map-policy.mjs";
import { groupEvents, locationCount } from "./map-clusters.mjs";
import { filterAdminEvents } from "./admin-filter.mjs";
import { eventToIcs, parseAttendees } from "./calendar-invite.mjs";
import { safeImageUrl } from "./image-url.mjs";
import {
  createSemanticSearchClient,
  rankSemanticMatches,
} from "./semantic-search.mjs";
import {
  languageFromBrowser,
  scaleLabels as scaleLabelsByLanguage,
  topicLabels as topicLabelsByLanguage,
  t,
} from "./i18n.mjs";
const EDITOR = import.meta.env.VITE_EDITOR === "1";
const STATIC = import.meta.env.VITE_STATIC === "1";
export const SHARE_URL =
  "https://github.com/agostontorok/nebenan/issues/new?template=event-share.yml";
export const FLAG_URL =
  "https://github.com/agostontorok/nebenan/issues/new?template=event-flag.yml";
type EventItem = {
  id: string;
  title: string;
  start: string;
  end?: string;
  all_day: boolean;
  venue: string;
  address: string;
  area?: string;
  description: string;
  topics: string[];
  scale: string;
  scale_evidence: string;
  price: string;
  free: boolean | null;
  lat: number | null;
  lon: number | null;
  coordinate_evidence?: string | null;
  status: string;
  ai_extracted?: boolean;
  poster_url?: string;
  image_url?: string | null;
  cancelled: boolean;
  review_reason: string;
  last_checked: string;
  provenance: {
    source_id: string;
    name: string;
    url: string;
    checked_at: string;
  }[];
};
type Source = {
  id: string;
  name: string;
  url: string;
  category: string;
  enabled: boolean;
  implemented: boolean;
  method: string;
  last_attempt: string;
  last_success: string;
  error: string;
  event_count: number;
  linked_social_profiles: { url: string }[];
  limitations: string;
  horizon_end?: string;
  discovery_error?: string;
};
type Candidate = {
  id: string;
  url: string;
  title: string;
  found_on: string;
  status: string;
};
type Status = {
  running: boolean;
  last_run: string;
  next_due: string;
  last_result: unknown;
  source_count: number;
  active_sources: number;
  event_count: number;
  review_count: number;
  collection_progress: unknown;
};
const safeUrl = (url: string) =>
  /^https?:\/\//i.test(url || "") ? url : undefined;
const dateLabel = (
  value: string,
  options: Intl.DateTimeFormatOptions = {
    dateStyle: "medium",
    timeStyle: "short",
  },
  language: "en" | "de" = "en",
) =>
  value && Number.isFinite(new Date(value).getTime())
    ? new Intl.DateTimeFormat(language === "de" ? "de-DE" : "en-GB", {
        timeZone: "Europe/Berlin",
        ...options,
      }).format(new Date(value))
    : t(language, "event.locationOpen");
async function api(path: string, method = "GET", body?: unknown) {
  const r = await fetch("/api" + path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    const data = await r.json().catch(() => null);
    throw new Error(
      typeof data?.detail === "string"
        ? data.detail
        : Array.isArray(data?.detail)
          ? data.detail.map((d: { msg: string }) => d.msg).join(" · ")
          : `Anfrage fehlgeschlagen (${r.status}). Bitte erneut versuchen.`,
    );
  }
  return r.status === 204 ? {} : r.json();
}
function Modal({
  title,
  onClose,
  closeLabel = "Close",
  children,
}: {
  title: string;
  onClose: () => void;
  closeLabel?: string;
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement;
    ref.current?.showModal();
    return () => previous?.focus();
  }, []);
  return (
    <dialog
      ref={ref}
      onCancel={onClose}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
      aria-labelledby="modal-title"
    >
      <div className="dialog-head">
        <h2 id="modal-title">{title}</h2>
        <button
          className="icon-button"
          onClick={onClose}
          aria-label={closeLabel}
        >
          ×
        </button>
      </div>
      {children}
    </dialog>
  );
}

function EventImage({
  url,
  title,
  className,
}: {
  url?: string | null;
  title: string;
  className: string;
}) {
  const src = safeImageUrl(url);
  const [failedSrc, setFailedSrc] = useState("");
  if (!src || failedSrc === src) return null;
  return (
    <img
      className={className}
      src={src}
      alt={title}
      loading="lazy"
      decoding="async"
      referrerPolicy="no-referrer"
      onError={() => setFailedSrc(src)}
    />
  );
}

function MapView({
  events,
  onSelect,
  onMapVisible,
  fitRequest,
  language,
}: {
  events: EventItem[];
  onSelect: (e: EventItem) => void;
  onMapVisible: (events: EventItem[]) => void;
  fitRequest: number;
  language: "en" | "de";
}) {
  const ref = useRef<HTMLDivElement>(null),
    map = useRef<L.Map | null>(null),
    layer = useRef<L.LayerGroup | null>(null),
    hasFitted = useRef(false),
    userInteracted = useRef(false);
  const eventsRef = useRef(events);
  const onMapVisibleRef = useRef(onMapVisible);
  eventsRef.current = events;
  onMapVisibleRef.current = onMapVisible;
  const reportVisible = useRef<() => void>(() => {});
  const [tileError, setTileError] = useState(false);
  const [zoom, setZoom] = useState(13);
  useEffect(() => {
    if (!ref.current) return;
    const m = L.map(ref.current, { scrollWheelZoom: false }).setView(
      [49.8728, 8.6512],
      13,
    );
    map.current = m;
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution:
        '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 19,
    })
      .on("tileerror", () => setTileError(true))
      .addTo(m);
    layer.current = L.layerGroup().addTo(m);
    m.on("dragstart zoomstart", () => {
      if (hasFitted.current) userInteracted.current = true;
    });
    reportVisible.current = () => {
      const m2 = map.current;
      if (!m2) return;
      const b = m2.getBounds();
      const visible = eventsRef.current.filter(
        (e) => e.lat != null && e.lon != null && b.contains([e.lat, e.lon]),
      );
      onMapVisibleRef.current(visible);
    };
    m.on("moveend zoomend", () => {
      setZoom(m.getZoom());
      reportVisible.current();
    });
    // Mobile CSS hides the map while the list is active. Observe actual layout
    // instead of inferring visibility from the selected page.
    let resizeFrame = 0;
    const observer = new ResizeObserver(([entry]) => {
      if (
        !entry ||
        entry.contentRect.width === 0 ||
        entry.contentRect.height === 0
      )
        return;
      cancelAnimationFrame(resizeFrame);
      resizeFrame = requestAnimationFrame(() => {
        m.invalidateSize({ pan: false });
      });
    });
    observer.observe(ref.current);
    return () => {
      observer.disconnect();
      cancelAnimationFrame(resizeFrame);
      m.remove();
      map.current = null;
    };
  }, []);
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    layer.current?.clearLayers();
    const coords: L.LatLngTuple[] = [];
    const groups = groupEvents(events, zoom);
    groups.forEach((g) => {
      const pos: L.LatLngTuple = [g.lat, g.lon];
      coords.push(pos);
      if (g.events.length === 1) {
        const e = g.events[0];
        L.marker(pos, {
          keyboard: true,
          title: e.title,
          icon: L.divIcon({
            className: "event-pin",
            html: `<span>1</span>`,
            iconSize: [32, 38],
            iconAnchor: [16, 38],
          }),
        })
          .on("click", () => onSelect(e))
          .addTo(layer.current!);
        return;
      }
      const count = g.events.length;
      L.marker(pos, {
        keyboard: true,
        title: `${count} ${language === "de" ? "Termine" : "events"}`,
        icon: L.divIcon({
          className: "cluster-pin",
          html: `<span>${count}</span>`,
          iconSize: [44, 44],
          iconAnchor: [22, 22],
        }),
      })
        .on("click", () => {
          const clusterBounds = L.latLngBounds(
            (g.events as EventItem[]).map(
              (e) => [e.lat!, e.lon!] as L.LatLngTuple,
            ),
          );
          m.fitBounds(clusterBounds, {
            padding: [45, 45],
            maxZoom: MAX_DRIFT_ZOOM,
            animate: true,
          });
        })
        .addTo(layer.current!);
    });
    if (
      shouldFitInitialMap({
        hasFitted: hasFitted.current || userInteracted.current,
        coordinateCount: coords.length,
      })
    ) {
      hasFitted.current = true;
      m.fitBounds(L.latLngBounds(coords), {
        padding: [45, 45],
        maxZoom: 14,
      });
      reportVisible.current();
    }
  }, [events, onSelect, language, zoom]);
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const coords: L.LatLngTuple[] = [];
    groupEvents(eventsRef.current, 13).forEach((g) => {
      coords.push([g.lat, g.lon]);
    });
    if (!coords.length) return;
    m.fitBounds(L.latLngBounds(coords), {
      padding: [45, 45],
      maxZoom: 14,
    });
    hasFitted.current = true;
    reportVisible.current();
  }, [fitRequest]);
  return (
    <div className="map-shell">
      <div
        ref={ref}
        className="map"
        aria-label={`${t(language, "results.map")} Darmstadt`}
      />
      {tileError && (
        <p className="map-warning">
          {language === "de"
            ? "Kartenbilder sind gerade nicht erreichbar. Alle Termine stehen weiterhin in der Liste."
            : "Map tiles are unavailable right now. All events remain available in the list."}
        </p>
      )}
      <div className="map-caption">
        <span className="live-dot" /> {t(language, "results.areaCaption")}{" "}
        <span>
          {locationCount(events)} {t(language, "results.placesDivider")}{" "}
          {events.filter((e) => e.lat != null && e.lon != null).length}{" "}
          {t(language, "results.events")}
        </span>
      </div>
    </div>
  );
}
function EventForm({
  event,
  onDone,
  language,
}: {
  event?: EventItem;
  onDone: () => void;
  language: "en" | "de";
}) {
  const tr = (key: string) => t(language, key);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const form = useRef<HTMLFormElement>(null);
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError("");
    try {
      const body: Record<string, unknown> = {};
      for (const key of [
        "title",
        "start",
        "end",
        "venue",
        "address",
        "description",
        "scale",
        "scale_evidence",
        "price",
        "source_url",
      ])
        body[key] = f.get(key) || null;
      body.topics = f.getAll("topics");
      body.free = f.get("free") === "" ? null : f.get("free") === "true";
      body.all_day = f.has("all_day");
      body.cancelled = f.has("cancelled");
      for (const key of ["lat", "lon"])
        body[key] = f.get(key) ? Number(f.get(key)) : null;
      if (event)
        body.status =
          (e.nativeEvent as SubmitEvent).submitter?.getAttribute("value") ||
          event.status;
      const file = f.get("poster") as File;
      if (file?.size) {
        if (file.size > 4 * 1024 * 1024)
          throw new Error(tr("form.maxImage"));
        body.poster = await new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result);
          reader.onerror = reject;
          reader.readAsDataURL(file);
        });
      }
      await api(
        event ? `/events/${event.id}` : "/submissions",
        event ? "PATCH" : "POST",
        event ? eventPatch(event, body) : body,
      );
      onDone();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form ref={form} onSubmit={submit} className="event-form">
      <p className="muted">
        {event
          ? tr("form.editHint")
          : tr("form.submitHint")}
      </p>
      {event?.poster_url && /^\/api\/posters\//.test(event.poster_url) && (
        <a href={event.poster_url} target="_blank" rel="noreferrer">
          {tr("form.posterView")}
        </a>
      )}
      <label>
        {tr("form.title")}<input name="title" required defaultValue={event?.title} />
      </label>
      <label>
        {tr("form.source")}
        <input
          name="source_url"
          type="url"
          placeholder="https://…"
          readOnly={!!event}
          defaultValue={event?.provenance?.[0]?.url}
        />
      </label>
      <div className="form-grid">
        <label>
          {tr("form.start")}
          <input
            name="start"
            type="datetime-local"
            step="1"
            defaultValue={berlinInput(event?.start)}
          />
        </label>
        <label>
          {tr("form.end")}
          <input
            name="end"
            type="datetime-local"
            step="1"
            defaultValue={berlinInput(event?.end)}
          />
        </label>
      </div>
      <label className="checkbox">
        <input name="all_day" type="checkbox" defaultChecked={event?.all_day} />{" "}
        {tr("form.allDay")}
      </label>
      <div className="form-grid">
        <label>
          {tr("form.venue")}
          <input name="venue" defaultValue={event?.venue} />
        </label>
        <label>
          {tr("form.address")}
          <input name="address" defaultValue={event?.address} />
        </label>
        <label>
            {tr("form.latitude")}
          <input
            name="lat"
            type="number"
            min="-90"
            max="90"
            step="any"
            defaultValue={event?.lat ?? ""}
          />
        </label>
        <label>
            {tr("form.longitude")}
          <input
            name="lon"
            type="number"
            min="-180"
            max="180"
            step="any"
            defaultValue={event?.lon ?? ""}
          />
        </label>
      </div>
      <label>
        {tr("form.description")}
        <textarea
          name="description"
          rows={4}
          defaultValue={event?.description}
        />
      </label>
      <fieldset className="topic-options">
        <legend>{tr("form.topics")}</legend>
        {Object.entries(topicLabelsByLanguage[language]).map(([value, label]) => (
          <label className="checkbox" key={value}>
            <input
              name="topics"
              type="checkbox"
              value={value}
              defaultChecked={event?.topics?.includes(value)}
            />
            {label}
          </label>
        ))}
      </fieldset>
      <div className="form-grid">
        <label>
          {tr("form.size")}
          <select name="scale" defaultValue={event?.scale || "unknown"}>
            {Object.entries(scaleLabelsByLanguage[language]).map(([v, label]) => (
              <option value={v} key={v}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          {tr("form.admission")}
          <select
            name="free"
            defaultValue={event?.free == null ? "" : String(event.free)}
          >
            <option value="">{tr("form.unknown")}</option>
            <option value="true">{tr("form.free")}</option>
            <option value="false">{tr("form.paid")}</option>
          </select>
        </label>
      </div>
      <label>
        {tr("form.evidence")}
        <input name="scale_evidence" defaultValue={event?.scale_evidence} />
      </label>
      <label>
        {tr("form.price")}
        <input name="price" defaultValue={event?.price} />
      </label>
      <label className="checkbox">
        <input
          type="checkbox"
          name="cancelled"
          defaultChecked={event?.cancelled}
        />{" "}
        {tr("form.cancelled")}
      </label>
      {!event && (
        <label>
          {tr("form.poster")}
          <input name="poster" type="file" accept="image/png,image/jpeg" />
          <small>
            {tr("form.posterHint")}
          </small>
        </label>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="form-actions">
        {event ? (
          <>
            <button
              className="primary"
              disabled={busy}
              name="action"
              value="published"
            >
              {tr("form.approve")}
            </button>
            <button disabled={busy} name="action" value={event.status}>
              {tr("form.save")}
            </button>
            <button
              className="danger"
              disabled={busy}
              name="action"
              value="rejected"
            >
              {tr("form.reject")}
            </button>
          </>
        ) : (
          <button className="primary" disabled={busy}>
            {busy ? tr("sources.running") : tr("form.submit")}
          </button>
        )}
      </div>
    </form>
  );
}

function InviteForm({
  event,
  language,
  onDone,
}: {
  event: EventItem;
  language: "en" | "de";
  onDone: () => void;
}) {
  const tr = (key: string) => t(language, key);
  const [value, setValue] = useState("");
  const [error, setError] = useState("");
  function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const raw = value.split(/[,;\s]+/).filter(Boolean);
    const attendees = parseAttendees(value);
    const uniqueRaw = new Set(raw.map((item) => item.toLocaleLowerCase()));
    if (!attendees.length || attendees.length !== uniqueRaw.size) {
      setError(tr("calendar.invalid"));
      return;
    }
    const ics = eventToIcs(event, attendees);
    const blobUrl = URL.createObjectURL(new Blob([ics], { type: "text/calendar;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = blobUrl;
    anchor.download = `${(event.title || "darmstadt-event").replace(/[^\p{L}\p{N}]+/gu, "-").replace(/^-|-$/g, "") || "darmstadt-event"}.ics`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(blobUrl);
    onDone();
  }
  return (
    <form className="event-form" onSubmit={submit}>
      <p className="muted">{tr("calendar.hint")}</p>
      <label>
        {tr("calendar.attendees")}
        <input
          type="text"
          required
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            setError("");
          }}
          placeholder="alex@example.com, sam@example.org"
          aria-label={tr("calendar.attendees")}
        />
      </label>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="form-actions">
        <button className="primary">{tr("calendar.download")}</button>
        <button type="button" onClick={onDone}>{tr("calendar.cancel")}</button>
      </div>
    </form>
  );
}

function App() {
  const [tab, setTab] = useState(EDITOR ? "review" : "discover"),
    [language, setLanguage] = useState<"en" | "de">(() => {
      try {
        return languageFromBrowser(
          window.localStorage.getItem("darmstadt-language"),
        );
      } catch {
        return "en";
      }
    }),
    [events, setEvents] = useState<EventItem[]>([]),
    [reviews, setReviews] = useState<EventItem[]>([]),
    [sources, setSources] = useState<Source[]>([]),
    [candidates, setCandidates] = useState<Candidate[]>([]),
    [status, setStatus] = useState<Status | null>(null),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [mode, setMode] = useState("week"),
    [from, setFrom] = useState(berlinDay()),
    [to, setTo] = useState(dateRange("week")[1]),
    [query, setQuery] = useState(""),
    [topic, setTopic] = useState(""),
    [scale, setScale] = useState(""),
    [free, setFree] = useState(false),
    [mobileMap, setMobileMap] = useState(false),
    [evening, setEvening] = useState(false),
    [timeVenue, setTimeVenue] = useState<"time" | "venue">("time"),
    [view, setView] = useState<"split" | "list">("split"),
    [isDesktop, setIsDesktop] = useState(() =>
      window.matchMedia("(min-width: 761px)").matches,
    ),
    [mapVisible, setMapVisible] = useState<EventItem[] | null>(null),
    [fitRequest, setFitRequest] = useState(0),
    [searchOpen, setSearchOpen] = useState(false),
    [adminQuery, setAdminQuery] = useState("");
  const [selected, setSelected] = useState<EventItem | null>(null),
    [editing, setEditing] = useState<EventItem | null>(null),
    [inviteFor, setInviteFor] = useState<EventItem | null>(null),
    [contribute, setContribute] = useState(false),
    [suggest, setSuggest] = useState(false),
    [pushing, setPushing] = useState(false),
    [pushNote, setPushNote] = useState("");
  const semanticClientRef = useRef<ReturnType<typeof createSemanticSearchClient> | null>(null);
  const [semanticScores, setSemanticScores] = useState<Record<string, number> | null>(null);
  const [semanticStatus, setSemanticStatus] = useState<
    "idle" | "loading" | "ready" | "fallback"
  >("idle");
  const tr = (key: string) => t(language, key);
  const topicLabels: Record<string, string> = topicLabelsByLanguage[language];
  const scales: Record<string, string> = scaleLabelsByLanguage[language];
  const formatDate = (
    value: string,
    options?: Intl.DateTimeFormatOptions,
  ) => dateLabel(value, options, language);
  const hourOf = (value: string) =>
    Number(formatDate(value, { hour: "2-digit", hourCycle: "h23" }).replace(/\D/g, ""));
  useEffect(() => {
    try {
      window.localStorage.setItem("darmstadt-language", language);
    } catch {
      // Private browsing can disable storage; the toggle still works in memory.
    }
    document.documentElement.lang = language;
  }, [language]);
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 761px)");
    const onChange = (e: MediaQueryListEvent) => setIsDesktop(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  async function refresh() {
    try {
      if (STATIC) {
        const data = await fetch("./data.json").then(async (r) => {
          if (!r.ok)
            throw new Error(
              `Anfrage fehlgeschlagen (${r.status}). Bitte erneut versuchen.`,
            );
          return r.json();
        });
        setEvents(data.events);
        setSources(data.sources);
        setCandidates(data.candidates || []);
        setStatus(data.status);
        setReviews(data.review);
        setError("");
        return;
      }
      const [a, b, c, d] = await Promise.all([
        api("/events"),
        api("/sources"),
        api("/status"),
        api("/review"),
      ]);
      setEvents(a.events);
      setSources(b.sources);
      setCandidates(b.candidates || []);
      setStatus(c);
      setReviews(d.events);
      setError("");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    refresh();
    if (STATIC) return;
    const timer = setInterval(refresh, 10000);
    return () => clearInterval(timer);
  }, []);
  const baseFiltered = useMemo(
    () =>
      filterEvents(events, {
        from,
        to,
        query: "",
        topic,
        scale,
        free,
      }) as EventItem[],
    [events, from, to, topic, scale, free],
  );
  const lexicalFiltered = useMemo(
    () =>
      filterEvents(events, {
        from,
        to,
        query,
        topic,
        scale,
        free,
      }) as EventItem[],
    [events, from, to, query, topic, scale, free],
  );
  const filtered = useMemo(() => {
    const base =
      !query.trim() || !semanticScores
        ? lexicalFiltered
        : (rankSemanticMatches(baseFiltered, query, semanticScores) as EventItem[]);
    return evening
      ? base.filter((e) => hourOf(e.start) >= 18)
      : base;
  }, [baseFiltered, lexicalFiltered, query, semanticScores, evening]);
  useEffect(() => {
    if (!query.trim()) {
      setSemanticScores(null);
      setSemanticStatus("idle");
      return;
    }
    let cancelled = false;
    setSemanticScores(null);
    setSemanticStatus("loading");
    semanticClientRef.current ||= createSemanticSearchClient();
    semanticClientRef.current
      .search(events, query, baseFiltered.map((event) => String(event.id)), {
        onProgress: () => {
          if (!cancelled) setSemanticStatus("loading");
        },
      })
      .then((scores: Record<string, number>) => {
        if (cancelled) return;
        setSemanticScores(scores);
        setSemanticStatus("ready");
      })
      .catch(() => {
        if (!cancelled) setSemanticStatus("fallback");
      });
    return () => {
      cancelled = true;
    };
  }, [events, query, baseFiltered]);
  useEffect(() => () => semanticClientRef.current?.dispose(), []);
  const topics = useMemo(
    () => [...new Set(events.flatMap((e) => e.topics || []))].sort(),
    [events],
  );
  const adminEvents = useMemo(
    () => filterAdminEvents(events, adminQuery) as EventItem[],
    [events, adminQuery],
  );
  const selectEvent = React.useCallback((e: EventItem) => setSelected(e), []);
  const mapShown = isDesktop ? view === "split" : mobileMap;
  const listEvents = useMemo(() => {
    if (mapShown && mapVisible)
      return [
        ...mapVisible,
        ...filtered.filter((e) => e.lat == null || e.lon == null),
      ];
    return filtered;
  }, [mapShown, mapVisible, filtered]);
  async function mutate(path: string, method: string, body?: unknown) {
    try {
      await api(path, method, body);
      await refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  }
  async function pushReview() {
    setPushing(true);
    setPushNote("");
    try {
      const result = (await api("/push", "POST")) as { status: string };
      setPushNote(
        result.status === "pushed"
          ? tr("admin.pushed")
          : tr("admin.pushUnchanged"),
      );
      await refresh();
    } catch (err) {
      setNotice(`${tr("admin.pushFailed")} ${(err as Error).message}`);
    } finally {
      setPushing(false);
    }
  }
  function chooseMode(value: string) {
    setMode(value);
    if (value !== "custom") {
      const r = dateRange(value);
      setFrom(r[0]);
      setTo(r[1]);
    }
  }
  const dayPartOf = (e: EventItem): "all" | "morning" | "afternoon" | "evening" => {
    if (e.all_day) return "all";
    const hour = hourOf(e.start);
    return hour < 12 ? "morning" : hour < 18 ? "afternoon" : "evening";
  };
  const timetable = useMemo(() => {
    const days: {
      day: string;
      total: number;
      slots: Record<"all" | "morning" | "afternoon" | "evening", EventItem[]>;
    }[] = [];
    const index = new Map<string, number>();
    listEvents.forEach((e) => {
      const key = berlinDay(new Date(e.start));
      let i = index.get(key);
      if (i === undefined) {
        i = days.length;
        index.set(key, i);
        days.push({
          day: key,
          total: 0,
          slots: { all: [], morning: [], afternoon: [], evening: [] },
        });
      }
      days[i].total++;
      days[i].slots[dayPartOf(e)].push(e);
    });
    return days;
  }, [listEvents]);
  const todayKey = berlinDay();
  const tomorrowKey = (() => {
    const d = new Date(todayKey + "T12:00:00Z");
    d.setUTCDate(d.getUTCDate() + 1);
    return d.toISOString().slice(0, 10);
  })();
  const slotsLabel = (key: string) =>
    key === "all"
      ? tr("schedule.allday")
      : key === "morning"
        ? `${tr("schedule.morning")} ${tr("schedule.morningRange")}`
        : key === "afternoon"
          ? `${tr("schedule.afternoon")} ${tr("schedule.afternoonRange")}`
          : `${tr("schedule.evening")} ${tr("schedule.eveningRange")}`;
  return (
    <>
      <header className="site-header">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setTab(EDITOR ? "review" : "discover");
          }}
        >
          <span className="brand-mark">
            n<span>•</span>
          </span>
          nebenan<span className="brand-city">DARMSTADT</span>
        </a>
        <nav aria-label={tr("nav.aria")}>
          {!EDITOR && (
            <button
              className={tab === "discover" ? "active" : ""}
              onClick={() => setTab("discover")}
            >
              {tr("nav.discover")}
            </button>
          )}
          {!EDITOR && (
            <button
              className={tab === "sources" ? "active" : ""}
              onClick={() => setTab("sources")}
            >
              {tr("nav.sources")}
            </button>
          )}
          {!STATIC && (
            <button
              className={tab === "review" ? "active" : ""}
              onClick={() => setTab("review")}
            >
              {tr("nav.review")} <span className="count">{reviews.length}</span>
            </button>
          )}
          {!STATIC && (
            <button
              className={tab === "admin" ? "active" : ""}
              onClick={() => setTab("admin")}
            >
              {tr("nav.admin")}
            </button>
          )}
        </nav>
        {tab === "discover" && !EDITOR && (
          searchOpen ? (
            <label className="header-search">
              <span aria-hidden="true">⌕</span>
              <input
                autoFocus
                aria-label={tr("filters.search")}
                placeholder={tr("filters.search")}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onBlur={() => {
                  if (!query.trim()) setSearchOpen(false);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Escape") {
                    setQuery("");
                    setSearchOpen(false);
                  }
                }}
              />
            </label>
          ) : (
            <button
              className="header-search-toggle"
              aria-label={tr("filters.search")}
              title={tr("filters.search")}
              onClick={() => setSearchOpen(true)}
            >
              <span aria-hidden="true">⌕</span>
            </button>
          )
        )}
        {!EDITOR &&
          (STATIC ? (
            <a
              className="header-contribute"
              href={SHARE_URL}
              target="_blank"
              rel="noopener noreferrer"
            >
              ＋ {tr("header.share")} ↗
            </a>
          ) : (
            <button
              className="header-contribute"
              onClick={() => setContribute(true)}
            >
              ＋ {tr("header.share")}
            </button>
          ))}
        <div className="language-switch" role="group" aria-label="Language / Sprache">
          <button
            className={language === "en" ? "selected" : ""}
            aria-pressed={language === "en"}
            onClick={() => setLanguage("en")}
          >
            EN
          </button>
          <button
            className={language === "de" ? "selected" : ""}
            aria-pressed={language === "de"}
            onClick={() => setLanguage("de")}
          >
            DE
          </button>
        </div>
      </header>
      <main>
        {tab === "discover" ? (
          <>
            <section className="timetable-page">
              <div className="filter-bar">
                  {query.trim() && (
                    <span
                      className={`semantic-status semantic-${semanticStatus}`}
                      role="status"
                      aria-live="polite"
                    >
                      {semanticStatus === "loading"
                        ? tr("filters.semanticLoading")
                        : semanticStatus === "ready"
                          ? tr("filters.semanticReady")
                          : tr("filters.semanticFallback")}
                    </span>
                  )}
                  <span className="chip-divider" aria-hidden="true" />
                  <button
                    className={`chip ${!topic && !free && mode !== "today" && !evening ? "chip-primary" : ""}`}
                    onClick={() => {
                      setTopic("");
                      setScale("");
                      setFree(false);
                      setEvening(false);
                      setQuery("");
                      chooseMode("week");
                      setView("split");
                      setMobileMap(false);
                      setFitRequest((n) => n + 1);
                    }}
                  >
                    {tr("chips.all")} <strong>{loading ? "…" : filtered.length}</strong>
                  </button>
                  <button
                    className={`chip ${mode === "today" && !evening ? "chip-primary" : ""}`}
                    onClick={() => {
                      if (mode === "today" && !evening) chooseMode("week");
                      else {
                        chooseMode("today");
                        setEvening(false);
                        setTopic("");
                        setScale("");
                        setFree(false);
                      }
                    }}
                  >
                    <span className="pulse-dot" aria-hidden="true" /> {tr("chips.now")}
                  </button>
                  <button
                    className={`chip ${evening ? "chip-primary" : ""}`}
                    onClick={() => {
                      chooseMode("today");
                      setEvening((v) => !v);
                      setTopic("");
                      setScale("");
                      setFree(false);
                    }}
                  >
                    <span className="material-symbols-outlined" aria-hidden="true">dark_mode</span>
                    {tr("chips.tonight")}
                  </button>
                  <button
                    className={`chip ${topic === "music" ? "chip-primary" : ""}`}
                    onClick={() => setTopic((prev) => (prev === "music" ? "" : "music"))}
                  >
                    <span className="material-symbols-outlined" aria-hidden="true">music_note</span>
                    {tr("chips.music")}
                  </button>
                  <button
                    className={`chip ${topic === "outdoors" ? "chip-primary" : ""}`}
                    onClick={() => setTopic((prev) => (prev === "outdoors" ? "" : "outdoors"))}
                  >
                    <span className="material-symbols-outlined" aria-hidden="true">fitness_center</span>
                    {tr("chips.sports")}
                  </button>
                  <button
                    className={`chip ${topic === "culture" ? "chip-primary" : ""}`}
                    onClick={() => setTopic((prev) => (prev === "culture" ? "" : "culture"))}
                  >
                    <span className="material-symbols-outlined" aria-hidden="true">theater_comedy</span>
                    {tr("chips.culture")}
                  </button>
                  <div className="view-toggle" role="group" aria-label={tr("filters.split")}>
                    <button
                      className={`view-toggle-btn ${view === "split" ? "active" : ""}`}
                      aria-pressed={view === "split"}
                      aria-label={view === "split" ? tr("results.list") : tr("filters.split")}
                      title={view === "split" ? tr("results.list") : tr("filters.split")}
                      onClick={() => {
                        if (view === "split") {
                          setView("list");
                          setMobileMap(true);
                        } else {
                          setView("split");
                          setMobileMap(false);
                        }
                      }}
                    >
                      <span className="material-symbols-outlined" aria-hidden="true">view_column</span>
                    </button>
                  </div>
                </div>
              {from > to && (
                <p role="alert" className="error">
                  {tr("filters.invalid")}
                </p>
              )}
              <div className="results-bar">
                <div className="results-title">
                  <h2>
                    {mode === "today" ? tr("schedule.title") : tr("results.events")}
                  </h2>
                  <em className="editorial-date">
                    {mode === "today"
                      ? formatDate(from + "T12:00:00Z", {
                          weekday: "long",
                          day: "numeric",
                          month: "long",
                        })
                      : `${formatDate(from + "T12:00:00Z", {
                          day: "numeric",
                          month: "short",
                        })} – ${formatDate(to + "T12:00:00Z", {
                          day: "numeric",
                          month: "short",
                        })}`}
                  </em>
                </div>
                <div className="results-tools">
                  <span className="slots-pill">
                    {loading ? "…" : listEvents.length} {tr("schedule.slots")}
                  </span>
                  <span className="sorted">
                    <span className="material-symbols-outlined" aria-hidden="true">swap_vert</span>
                    {tr("schedule.sorted")}
                  </span>
                  <button
                    className={`toggle-time ${timeVenue === "venue" ? "pressed" : ""}`}
                    aria-pressed={timeVenue === "venue"}
                    onClick={() =>
                      setTimeVenue((v) => (v === "time" ? "venue" : "time"))
                    }
                  >
                    {tr("schedule.toggle")}
                  </button>
                </div>
              </div>
              {error && (
                <div className="error" role="alert">
                  {error} <button onClick={refresh}>Erneut laden</button>
                </div>
              )}
              <div
                className={`tt-layout ${view === "list" ? "list-only" : ""} ${mobileMap ? "show-map" : ""}`}
              >
                <div className="tt-col" aria-live="polite">
                  {loading ? (
                    <div className="empty">
                      <span className="loading-spinner" />
                      <h3>{tr("loading")}</h3>
                    </div>
                  ) : listEvents.length ? (
                    timetable.map(
                      (d) => (
                        <section className="tt-day" key={d.day}>
                          <header className="tt-day-head">
                            <span className="material-symbols-outlined" aria-hidden="true">
                              {d.day === todayKey
                                ? "today"
                                : d.day === tomorrowKey
                                  ? "event"
                                  : "calendar_month"}
                            </span>
                            <h3>
                              {d.day === todayKey
                                ? tr("schedule.dayToday")
                                : d.day === tomorrowKey
                                  ? tr("schedule.dayTomorrow")
                                  : formatDate(d.day + "T12:00:00Z", {
                                      weekday: "long",
                                    })}
                            </h3>
                            <em>
                              {formatDate(d.day + "T12:00:00Z", {
                                day: "numeric",
                                month: "long",
                              })}
                            </em>
                            <span className="tt-count">
                              {d.total} {tr("results.events")}
                            </span>
                          </header>
                          {(["all", "morning", "afternoon", "evening"] as const).map(
                            (k) =>
                              d.slots[k].length > 0 && (
                                <section className="tt-group" key={k}>
                                  <header className="tt-group-head">
                                    <span className="material-symbols-outlined" aria-hidden="true">
                                      {k === "all"
                                        ? "calendar_today"
                                        : k === "morning"
                                          ? "wb_sunny"
                                          : k === "afternoon"
                                            ? "schedule"
                                            : "nightlight"}
                                    </span>
                                    <h3>{slotsLabel(k)}</h3>
                                    <span className="tt-count">
                                      {d.slots[k].length} {tr("results.events")}
                                    </span>
                                  </header>
                                  {d.slots[k].map((e) => (
                                    <button
                                      className={`tt-row ${e.cancelled ? "cancelled" : ""}`}
                                      key={e.id}
                                      onClick={() => setSelected(e)}
                                    >
                                <div className="tt-time">
                                  {timeVenue === "time" ? (
                                    <>
                                      <strong>
                                        {e.all_day
                                          ? tr("event.allDay")
                                          : formatDate(e.start, {
                                              hour: "2-digit",
                                              minute: "2-digit",
                                            })}
                                      </strong>
                                      {e.end && !e.all_day && (
                                        <span>
                                          {formatDate(e.end, {
                                            hour: "2-digit",
                                            minute: "2-digit",
                                          })}
                                        </span>
                                      )}
                                    </>
                                  ) : (
                                    <>
                                      <strong>
                                        {e.venue || tr("event.locationOpen")}
                                      </strong>
                                      <span>
                                        {e.area && e.area !== "Darmstadt"
                                          ? e.area
                                          : formatDate(e.start, {
                                              hour: "2-digit",
                                              minute: "2-digit",
                                            })}
                                      </span>
                                    </>
                                  )}
                                </div>
                                <div className="tt-main">
                                  <div className="tt-tags">
                                    {e.topics?.[0] && (
                                      <span
                                        className={`cat-chip cat-${topics.indexOf(e.topics[0]) >= 0 ? topics.indexOf(e.topics[0]) % 3 : 0}`}
                                      >
                                        {topicLabels[e.topics[0]] || e.topics[0]}
                                      </span>
                                    )}
                                    {e.cancelled && (
                                      <span className="cancel-tag">
                                        {tr("event.cancelled")}
                                      </span>
                                    )}
                                  </div>
                                  <h3 className="tt-title">{e.title}</h3>
                                  <p className="tt-meta">
                                    <em>
                                      {e.description
                                        ? e.description.length > 140
                                          ? e.description.trim().slice(0, 140) + "…"
                                          : e.description
                                        : tr("detail.more")}
                                    </em>
                                    <span>
                                      {" "}
                                      · {e.venue || tr("event.locationOpen")}
                                    </span>
                                    {e.area && e.area !== "Darmstadt" && (
                                      <span> · {e.area}</span>
                                    )}
                                  </p>
                                </div>
                                <div className="tt-side">
                                  <EventImage
                                    url={e.image_url || e.poster_url}
                                    title={e.title}
                                    className="tt-thumb"
                                  />
                                  <span
                                    className={
                                      e.free === true ? "free-badge" : "price-badge"
                                    }
                                  >
                                    {e.free === true
                                      ? tr("event.free")
                                      : e.price || tr("detail.noPrice")}
                                  </span>
                                  <span className="details-link">
                                    {tr("schedule.details")} ↗
                                  </span>
                                </div>
                              </button>
                            ))}
                          </section>
                        ),
                      )}
                        </section>
                      ),
                    )
                  ) : (
                    <div className="empty">
                      <div className="empty-symbol">✳</div>
                      <h3>{tr("empty.heading")}</h3>
                      <p>
                        {events.length
                          ? tr("empty.filtered")
                          : tr("empty.none")}
                      </p>
                      <button
                        onClick={() => {
                          setQuery("");
                          setTopic("");
                          setScale("");
                          setFree(false);
                          setEvening(false);
                          setView("split");
                          setMobileMap(false);
                          chooseMode("week");
                          setFitRequest((n) => n + 1);
                        }}
                      >
                        {tr("empty.reset")}
                      </button>
                    </div>
                  )}
                </div>
                <aside className="map-col">
                  <MapView
                    events={filtered}
                    onSelect={selectEvent}
                    onMapVisible={setMapVisible}
                    fitRequest={fitRequest}
                    language={language}
                  />
                </aside>
              </div>
            </section>
          </>
        ) : tab === "sources" ? (
          <section className="workspace">
            <p className="eyebrow">{tr("sources.eyebrow")}</p>
            <h1>
              {tr("sources.titleA")}
              <br />
              <em>{tr("sources.titleB")}</em>
            </h1>
            <p className="intro">
              {tr("sources.intro")}
            </p>
            <div className="status-grid">
              <div>
                <strong>
                  {sources.filter((s) => s.implemented && s.enabled).length}
                </strong>
                <span>{tr("sources.active")}</span>
              </div>
              <div>
                <strong>{sources.length}</strong>
                <span>{tr("sources.directory")}</span>
              </div>
              <div>
                <strong>{events.length}</strong>
                <span>{tr("sources.published")}</span>
              </div>
              {!STATIC && (
                <div>
                  <strong>{reviews.length}</strong>
                  <span>{tr("sources.review")}</span>
                </div>
              )}
            </div>
            <div className="collection-panel">
              <div>
                <h3>
                  {status?.running
                    ? tr("sources.running")
                    : tr("sources.idle")}
                </h3>
                <p>
                  {tr("sources.last")}: {formatDate(status?.last_run || "")} · {tr("sources.next")}: {formatDate(status?.next_due || "")}
                </p>
                <p>
                  {tr("sources.weekly")}
                </p>
                {status?.running && (
                  <p role="status">
                    {typeof status.collection_progress === "string"
                      ? status.collection_progress
                      : tr("sources.progress")}
                  </p>
                )}
              </div>
              {!STATIC && (
                <button
                  className="primary"
                  disabled={status?.running}
                  onClick={() => mutate("/collect", "POST")}
                >
                  {status?.running ? tr("sources.running") : tr("sources.update")}
                </button>
              )}
            </div>
            <p className="capability-note">
              {tr("sources.capability")}
            </p>
            {error && (
              <p className="error" role="alert">
                {error}
              </p>
            )}
            <div className="section-title">
              <h2>{tr("sources.heading")}</h2>
              {!STATIC && (
                <button onClick={() => setSuggest(true)}>
                  ＋ {tr("sources.suggest")}
                </button>
              )}
            </div>
            <div className="source-grid">
              {sources.map((s) => (
                <article className="source-card" key={s.id}>
                  <div className="source-top">
                    <span
                      className={`source-state ${s.implemented ? "implemented" : ""}`}
                    >
                      {s.implemented
                        ? s.enabled
                          ? tr("sources.collectorActive")
                          : tr("sources.collectorPaused")
                        : tr("sources.researched")}
                    </span>
                    {s.implemented && !STATIC && (
                      <label className="checkbox">
                        <input
                          type="checkbox"
                          aria-label={`${s.name} automatisch sammeln`}
                          checked={s.enabled}
                          onChange={(e) =>
                            mutate(`/sources/${s.id}`, "PATCH", {
                              enabled: e.target.checked,
                            })
                          }
                        />{" "}
                        {tr("sources.enabled")}
                      </label>
                    )}
                  </div>
                  <h3>
                    <a href={safeUrl(s.url)} target="_blank" rel="noreferrer">
                      {s.name} ↗
                    </a>
                  </h3>
                  <p>
                    {s.category} {s.method && `· ${s.method}`}
                  </p>
                  {s.implemented && (
                    <small>
                      {s.event_count || 0} {tr("sources.events")} · {tr("sources.lastSuccess")}:{" "}
                      {formatDate(s.last_success)}
                    </small>
                  )}
                  {s.horizon_end && (
                    <p>
                      {tr("sources.preview")} {" "}
                      {formatDate(s.horizon_end, { dateStyle: "medium" })}
                    </p>
                  )}
                  {s.discovery_error && (
                    <p className="source-error">
                      {tr("sources.discoveryError")}: {s.discovery_error}
                    </p>
                  )}
                  {s.error && (
                    <p className="source-error">
                      {tr("sources.fetchError")}: {s.error}
                    </p>
                  )}
                  {s.limitations && <p className="muted">{s.limitations}</p>}
                  {s.linked_social_profiles?.length > 0 && (
                    <div className="social-links">
                      {s.linked_social_profiles.map((p, i) => (
                        <a
                          key={p.url}
                          href={safeUrl(p.url)}
                          target="_blank"
                          rel="noreferrer"
                        >
                          {tr("sources.social")} {i + 1} ↗
                        </a>
                      ))}
                    </div>
                  )}
                </article>
              ))}
            </div>
            {candidates.length > 0 && (
              <>
                <h2 className="candidate-heading">{tr("sources.discoveredLinks")}</h2>
                <p className="muted">
                  {tr("sources.acceptHint")}
                </p>
                {candidates.map((c) => (
                  <div className="candidate" key={c.id}>
                    <div>
                      <a href={safeUrl(c.url)} target="_blank" rel="noreferrer">
                        {c.title || c.url} ↗
                      </a>
                      <small>
                        {tr("sources.foundOn")}: {c.found_on} · {c.status}
                      </small>
                    </div>
                    {!STATIC && !["accepted", "rejected"].includes(c.status) && (
                      <div>
                        <button
                          onClick={() =>
                            mutate(`/candidates/${c.id}`, "PATCH", {
                              status: "accepted",
                            })
                          }
                        >
                          {tr("sources.accept")}
                        </button>
                        <button
                          onClick={() =>
                            mutate(`/candidates/${c.id}`, "PATCH", {
                              status: "rejected",
                            })
                          }
                        >
                          {tr("sources.reject")}
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </>
            )}
          </section>
        ) : !STATIC && tab === "review" ? (
          <section className="workspace">
            <p className="eyebrow">{tr("review.eyebrow")}</p>
            <h1>
              {tr("review.titleA")}
              <br />
              <em>{tr("review.titleB")}</em>
            </h1>
            <p className="intro">
              {tr("review.intro")}
            </p>
            {reviews.length === 0 ? (
              <div className="empty">
                <div className="empty-symbol">✓</div>
                <h3>{tr("review.empty")}</h3>
                <p>
                  {tr("review.emptyCopy")}
                </p>
              </div>
            ) : (
              reviews.map((e) => (
                <article className="review-card" key={e.id}>
                  <div>
                    <span className="source-state">{tr("review.badge")}</span>
                    <h3>{e.title}</h3>
                    <p>
                      {formatDate(e.start)} · {e.venue || tr("event.locationOpen")}
                    </p>
                    <p className="muted">
                      {e.review_reason || tr("review.defaultReason")}
                    </p>
                  </div>
                  {!STATIC && (
                    <button className="primary" onClick={() => setEditing(e)}>
                      {tr("review.inspect")}
                    </button>
                  )}
                </article>
              ))
            )}
          </section>
        ) : !STATIC && tab === "admin" ? (
          <section className="workspace admin-workspace">
            <p className="eyebrow">
              {tr("review.eyebrow")}
              {EDITOR && <> · {tr("admin.editor")}</>}
            </p>
            <h1>{tr("admin.heading")}</h1>
            <p className="intro">{tr("admin.intro")}</p>
            {EDITOR && !STATIC && (
              <p className="collection-panel">
                <button
                  className="primary"
                  disabled={pushing}
                  onClick={pushReview}
                >
                  {pushing ? tr("admin.publishing") : tr("admin.publish")}
                </button>
                {pushNote && <span className="muted"> {pushNote}</span>}
              </p>
            )}
            <label className="search admin-search">
              <span aria-hidden="true">⌕</span>
              <input
                aria-label={tr("admin.search")}
                placeholder={tr("admin.search")}
                value={adminQuery}
                onChange={(e) => setAdminQuery(e.target.value)}
              />
              {adminQuery && (
                <button onClick={() => setAdminQuery("")} aria-label={tr("filters.clear")}>
                  ×
                </button>
              )}
            </label>
            {adminEvents.length === 0 ? (
              <div className="empty">
                <div className="empty-symbol">⌕</div>
                <h3>{tr("admin.empty")}</h3>
              </div>
            ) : (
              <div className="admin-event-list">
                {adminEvents.map((e) => (
                  <article className="review-card" key={e.id}>
                    <div>
                      <span className="source-state implemented">{e.cancelled ? tr("event.cancelled") : tr("admin.published")}</span>
                      <h3>{e.title}</h3>
                      <p>{formatDate(e.start)} · {e.venue || tr("event.locationOpen")}</p>
                    </div>
                    {!STATIC && (
                      <button className="primary" onClick={() => setEditing(e)}>
                        {tr("admin.edit")}
                      </button>
                    )}
                  </article>
                ))}
              </div>
            )}
            {adminEvents.length > 0 && events.filter((e) => e.status === "published").length > adminEvents.length && (
              <p className="muted">{tr("admin.showing")}</p>
            )}
          </section>
        ) : (
          null
        )}
        {notice && (
          <div className="toast" role="status">
            {notice}
            <button
              onClick={() => setNotice("")}
              aria-label={tr("modal.close")}
            >
              ×
            </button>
          </div>
        )}
      </main>
      <footer>
        <a
          className="footer-brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setTab(EDITOR ? "review" : "discover");
          }}
        >
          nebenan<span>•</span>
        </a>
        <p className="footer-rights">
          {tr("footer.rights").replace("{year}", String(new Date().getFullYear()))}
          {" "}· {tr("footer.guide")}
        </p>
        <div className="footer-links">
          <span>{tr("footer.imprint")}</span>
          <span>{tr("footer.privacy")}</span>
          <span>{tr("footer.contact")}</span>
        </div>
      </footer>
      {selected && (
        <Modal title={selected.title} closeLabel={tr("modal.close")} onClose={() => setSelected(null)}>
          <EventImage
            url={selected.image_url || selected.poster_url}
            title={selected.title}
            className="detail-image"
          />
          <div className="detail-tags">
            {selected.topics?.map((t) => (
              <span key={t}>{topicLabels[t] || t}</span>
            ))}
            {selected.cancelled && <span className="cancel-tag">{tr("event.cancelled")}</span>}
          </div>
          <dl className="detail-grid">
            <div>
              <dt>{tr("detail.when")}</dt>
              <dd>
                {formatDate(
                  selected.start,
                  selected.all_day ? { dateStyle: "full" } : undefined,
                )}
                {selected.all_day ? ` · ${tr("event.allDay")}` : ""}
                {selected.end && (
                  <>
                    <br />
                    {language === "de" ? "bis" : "until"}{" "}
                    {selected.all_day
                      ? formatDate(
                          new Date(
                            new Date(selected.end).getTime() - 1,
                          ).toISOString(),
                          { dateStyle: "full" },
                        )
                      : formatDate(selected.end)}
                  </>
                )}
              </dd>
            </div>
            <div>
              <dt>{tr("detail.where")}</dt>
              <dd>
                {selected.venue || tr("detail.noLocation")}
                <br />
                {selected.address}
                {selected.lat == null && (
                  <small>{tr("detail.noMap")}</small>
                )}
                {selected.coordinate_evidence?.startsWith("Approximate") && (
                  <small>
                    {language === "de"
                      ? "Ungefährer Gemeindeort – genauen Veranstaltungsort prüfen"
                      : "Approximate municipality location – check the exact venue"}
                  </small>
                )}
              </dd>
            </div>
            <div>
              <dt>{tr("detail.admission")}</dt>
              <dd>
                {selected.free === true
                  ? tr("event.free")
                  : selected.price || tr("detail.noPrice")}
                {selected.free === true && selected.price
                  ? ` · ${selected.price}`
                  : ""}
              </dd>
            </div>
            <div>
              <dt>{tr("detail.size")}</dt>
              <dd>
                {scales[selected.scale] || tr("event.sizeOpen")}
                {selected.scale_evidence && (
                  <small>{selected.scale_evidence}</small>
                )}
              </dd>
            </div>
          </dl>
          <p className="description">
            {selected.description ||
              tr("detail.more")}
          </p>
          {selected.ai_extracted && (
            <div className="ai-notice">
              <p>
                <strong>{tr("detail.aiTitle")}</strong> {tr("detail.aiWarning")}
              </p>
              <a
                href={`${FLAG_URL}?title=${encodeURIComponent(
                  `[Flag] ${selected.title} (${formatDate(selected.start, { dateStyle: "short" })})`,
                )}`}
                target="_blank"
                rel="noreferrer"
              >
                {tr("detail.aiFlag")} ↗
              </a>
            </div>
          )}
          <div className="provenance">
            <h3>{tr("detail.source")}</h3>
            {selected.provenance?.map((p, i) => (
              <div key={i}>
                <a href={safeUrl(p.url)} target="_blank" rel="noreferrer">
                  {p.name || tr("detail.original")} ↗
                </a>
                <small>{tr("detail.checked")}: {formatDate(p.checked_at)}</small>
              </div>
            ))}
            <p>
              {tr("detail.checkSource")}
            </p>
          </div>
          <div className="detail-actions">
            <button
              className="primary"
              onClick={() => {
                setInviteFor(selected);
                setSelected(null);
              }}
            >
              {tr("calendar.create")}
            </button>
            {!STATIC && (
              <button
                onClick={() => {
                  setEditing(selected);
                  setSelected(null);
                }}
              >
                {tr("detail.edit")}
              </button>
            )}
          </div>
        </Modal>
      )}
      {inviteFor && (
        <Modal
          title={`${tr("calendar.title")}: ${inviteFor.title}`}
          closeLabel={tr("modal.close")}
          onClose={() => setInviteFor(null)}
        >
          <InviteForm
            event={inviteFor}
            language={language}
            onDone={() => setInviteFor(null)}
          />
        </Modal>
      )}
      {!STATIC && contribute && (
        <Modal
          title={tr("header.share")}
          closeLabel={tr("modal.close")}
          onClose={() => setContribute(false)}
        >
          <EventForm
            language={language}
            onDone={() => {
              setContribute(false);
              setNotice(tr("toast.submitted"));
              refresh();
            }}
          />
        </Modal>
      )}
      {!STATIC && editing && (
        <Modal title={tr("review.inspect")} closeLabel={tr("modal.close")} onClose={() => setEditing(null)}>
          <EventForm
            event={editing}
            language={language}
            onDone={() => {
              setEditing(null);
              setNotice(tr("toast.saved"));
              refresh();
            }}
          />
        </Modal>
      )}
      {!STATIC && suggest && (
        <Modal
          title={tr("suggest.title")}
          closeLabel={tr("modal.close")}
          onClose={() => setSuggest(false)}
        >
          <form
            className="event-form"
            onSubmit={async (e) => {
              e.preventDefault();
              const data = new FormData(e.currentTarget);
              try {
                await api("/sources/suggest", "POST", {
                  url: data.get("url"),
                  title: data.get("title"),
                });
                setSuggest(false);
                setNotice(tr("toast.sourceSuggested"));
                refresh();
              } catch (err) {
                setError((err as Error).message);
              }
            }}
          >
            <p>
              {tr("suggest.copy")}
            </p>
            <label>
              {tr("suggest.name")}
              <input name="title" required />
            </label>
            <label>
              {tr("suggest.url")}
              <input name="url" type="url" required placeholder="https://…" />
            </label>
            {error && (
              <p className="error" role="alert">
                {error}
              </p>
            )}
            <button className="primary">{tr("suggest.submit")}</button>
          </form>
        </Modal>
      )}
    </>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
