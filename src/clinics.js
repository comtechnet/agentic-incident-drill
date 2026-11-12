import { readFileSync } from 'node:fs';

const DAYS = ['mon', 'tue', 'wed', 'thu', 'fri'];
const { clinics } = JSON.parse(
  readFileSync(new URL('../data/clinics.json', import.meta.url), 'utf8'),
);

export function formatHours(range) {
  const [open, close] = range.split('-');
  return { open, close };
}

export function toResult(clinic) {
  return {
    id: clinic.id,
    name: clinic.name,
    town: clinic.town,
    services: clinic.services,
    weekdays: Object.fromEntries(DAYS.map((d) => [d, formatHours(clinic.hours[d])])),
    saturday: clinic.hours.sat ? formatHours(clinic.hours.sat) : null,
  };
}

export function findByTown(town) {
  const t = town.trim().toLowerCase();
  return clinics.filter((c) => c.town.toLowerCase() === t).map(toResult);
}

export function towns() {
  return [...new Set(clinics.map((c) => c.town))];
}
