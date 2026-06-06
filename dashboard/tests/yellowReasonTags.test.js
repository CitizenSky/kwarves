import { describe, it, expect, vi } from 'vitest';

vi.mock('../src/i18n.js', () => ({
  t: (key) => key,
  formatMaybe: (v, d) => v ?? d
}));

const { reasonTagList, nextCheckList, candidateChip, yellowTagLabels } = await import('../src/logic/yellowReasonTags.js');

describe('yellowTagLabels', () => {
  it('has predefined tag labels', () => {
    expect(yellowTagLabels.Y_NTR_LOW).toBeTruthy();
    expect(yellowTagLabels.Y_LONG_PERIOD).toBeTruthy();
    expect(yellowTagLabels.Y_MANUAL_REVIEW).toBeTruthy();
  });
});

describe('reasonTagList', () => {
  it('renders tags when provided', () => {
    const result = reasonTagList(['Y_NTR_LOW', 'Y_DATA_GAP']);
    expect(result).toContain('reason-tag-list');
    expect(result).toContain('Y_NTR_LOW');
    expect(result).toContain('Y_DATA_GAP');
  });
  it('shows fallback when empty', () => {
    const result = reasonTagList([]);
    expect(result).toContain('no_yellow_reason_tags');
  });
});

describe('candidateChip', () => {
  it('renders a chip with TIC and evidence score', () => {
    const result = candidateChip({ tic: 12345, evidenceScore: 85 });
    expect(result).toContain('12345');
    expect(result).toContain('85');
    expect(result).toContain('chip');
  });
});
