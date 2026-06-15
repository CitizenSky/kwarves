const HABITABLE_ZONE_CLASSES = new Set(["KONSERVATIVE_HZ", "OPT_HZ_INNEN"]);

export function normalizeHabitableZone(value) {
  return String(value ?? "").trim().toUpperCase();
}

export function isHabitableZoneClass(value) {
  return HABITABLE_ZONE_CLASSES.has(normalizeHabitableZone(value));
}

export function isHabitableZoneCandidate(candidate) {
  return isHabitableZoneClass(candidate?.hz ?? candidate?.hzMarkierung ?? candidate?.hz_markierung);
}

