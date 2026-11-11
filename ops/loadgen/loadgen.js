// Synthetic "users": a steady trickle of lookups spread across the five fictional towns.
const TARGET = process.env.TARGET ?? 'http://clinic-hours:8070';
const RPS = Number(process.env.RPS ?? 2);
const towns = ['Fernhill', 'Millbrook', 'Cedar Falls', 'Ashby', 'Quarry Point'];
let i = 0;
setInterval(() => {
  const town = towns[i++ % towns.length];
  fetch(`${TARGET}/clinics?town=${encodeURIComponent(town)}`, { signal: AbortSignal.timeout(3000) })
    .then((r) => r.body?.cancel()).catch(() => {});
}, 1000 / RPS);
console.log(`loadgen: ${RPS} req/s against ${TARGET}`);
