/* Pure helpers shared by the browser client and dependency-free contract tests. */
(function (root, factory) { if (typeof module === 'object') module.exports = factory(); else root.SkylineLogic = factory(); }(typeof self !== 'undefined' ? self : this, function () {
  function buildPayload(itinerary, cabin, values) { const passengers = []; for (let i = 0; values.has(`passengers[${i}].given_name`); i++) passengers.push({ given_name: values.get(`passengers[${i}].given_name`), surname: values.get(`passengers[${i}].surname`) }); const channel = values.get('channel'); return { leg_ids: itinerary.leg_ids || (itinerary.legs || []).map(x => x.id), cabin, passengers, channel, ...(channel === 'AGENCY' ? { agency_id: values.get('agency_id'), agent_id: values.get('agent_id') } : {}) }; }
  function countdownText(seconds) { return seconds ? `Time remaining: ${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}` : 'Retention expired. Payment is no longer available.'; }
  function requestId(cryptoProvider, random = Math.random) {
    const provider = cryptoProvider || (typeof globalThis !== 'undefined' ? globalThis.crypto : null);
    if (provider && typeof provider.randomUUID === 'function') return provider.randomUUID();
    const bytes = new Uint8Array(16);
    if (provider && typeof provider.getRandomValues === 'function') provider.getRandomValues(bytes);
    else for (let index = 0; index < bytes.length; index++) bytes[index] = Math.floor(random() * 256);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }
  return { buildPayload, countdownText, requestId };
}));
