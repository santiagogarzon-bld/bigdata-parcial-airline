/* Pure helpers shared by the browser client and dependency-free contract tests. */
(function (root, factory) { if (typeof module === 'object') module.exports = factory(); else root.SkylineLogic = factory(); }(typeof self !== 'undefined' ? self : this, function () {
  function buildPayload(itinerary, cabin, values) { const passengers = []; for (let i = 0; values.has(`passengers[${i}].given_name`); i++) passengers.push({ given_name: values.get(`passengers[${i}].given_name`), surname: values.get(`passengers[${i}].surname`) }); const channel = values.get('channel'); return { leg_ids: itinerary.leg_ids || (itinerary.legs || []).map(x => x.id), cabin, passengers, channel, ...(channel === 'AGENCY' ? { agency_id: values.get('agency_id'), agent_id: values.get('agent_id') } : {}) }; }
  function countdownText(seconds) { return seconds ? `Time remaining: ${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}` : 'Retention expired. Payment is no longer available.'; }
  return { buildPayload, countdownText };
}));
