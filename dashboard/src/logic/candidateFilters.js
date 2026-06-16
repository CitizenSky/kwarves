import { isSpcPrepCandidate, matrixText } from './colorFor.js';
import { isHabitableZoneCandidate } from './habitableZone.js';
import { evaluateVvt } from './vvtScoring.js';

export function isVvtCandidate(candidate) {
  const vvt = candidate?.vvtStatus ? candidate : evaluateVvt(candidate);
  const text = matrixText(candidate);
  return (
    ["EXOFOP_READY", "NEEDS_REVIEW"].includes(candidate?.vvtStatus || vvt.vvtStatus) ||
    candidate?.color === "green" ||
    /SPC_STRONG|SPC_FOLLOWUP_READY|SPC_RV_NEEDED/.test(text)
  ) && !/FALSE_POSITIVE|RED_FP|EB_RISK|REJECTED|IGNORE/.test(text);
}

export function candidateMatchesColorFilter(candidate, colorFilter = 'all') {
  switch (colorFilter) {
    case 'all':
      return true;
    case 'violet':
      return isHabitableZoneCandidate(candidate);
    case 'spc-prep':
      return isSpcPrepCandidate(candidate);
    case 'vvt':
      return isVvtCandidate(candidate);
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
