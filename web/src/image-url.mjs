const GENERIC_ASSET = /(?:^|[/_.-])(favicon|favicons|logo|logos|brand|branding|sprite|sprites|icon|icons)(?:$|[/_.-])/i;

function isPrivateHost(hostname) {
  const host = hostname.toLowerCase().replace(/^\[|\]$/g, "");
  if (
    host === "localhost" ||
    host.endsWith(".localhost") ||
    host.endsWith(".local") ||
    host.endsWith(".internal") ||
    host === "::1" ||
    host.startsWith("fc") ||
    host.startsWith("fd") ||
    host.startsWith("fe80:")
  ) {
    return true;
  }
  const octets = host.split(".").map((part) => Number(part));
  if (octets.length !== 4 || octets.some((part) => !Number.isInteger(part))) {
    return false;
  }
  return (
    octets[0] === 10 ||
    octets[0] === 127 ||
    (octets[0] === 172 && octets[1] >= 16 && octets[1] <= 31) ||
    (octets[0] === 192 && octets[1] === 168) ||
    (octets[0] === 169 && octets[1] === 254)
  );
}

export function safeImageUrl(value) {
  if (typeof value !== "string" || !value.trim()) return "";
  const candidate = value.trim();
  if (/^\/api\/posters\//.test(candidate)) return candidate;
  if (!/^https?:\/\//i.test(candidate)) return "";
  try {
    const parsed = new URL(candidate);
    if (
      !["http:", "https:"].includes(parsed.protocol) ||
      parsed.username ||
      parsed.password ||
      isPrivateHost(parsed.hostname) ||
      GENERIC_ASSET.test(parsed.pathname)
    ) {
      return "";
    }
    return parsed.toString();
  } catch {
    return "";
  }
}
