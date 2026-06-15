import { isSpcPrepCandidate } from './colorFor.js';
import { isHabitableZoneCandidate } from './habitableZone.js';

export function candidateMatchesColorFilter(candidate, colorFilter = 'all') {
  switch (colorFilter) {
    case 'all':
      return true;
    case 'violet':
      return isHabitableZoneCandidate(candidate);
    case 'spc-prep':
      return isSpcPrepCandidate(candidate);
    case 'yellow':
      return candidate?.color === 'yellow' && !isSpcPrepCandidate(candidate);
    case 'green':
    case 'red':
    case 'gray':
      return candidate?.color === colorFilter;
    default:
      return false;
  }
}
