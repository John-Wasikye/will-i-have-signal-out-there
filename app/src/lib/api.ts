/**
 * The address of one sample lookup. The API serves /sample at the root of its address
 * (docs/platform/openapi-serving-template.yaml). The key is encoded, so it cannot change the
 * address.
 */
export function sampleUrl(baseUrl: string, key: string): string {
  return `${baseUrl.replace(/\/$/, '')}/sample?key=${encodeURIComponent(key)}`
}
