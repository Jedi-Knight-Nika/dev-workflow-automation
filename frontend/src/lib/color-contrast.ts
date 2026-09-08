type RGB = [number, number, number];

function rgb(hex: string): RGB {
  return [1, 3, 5].map((offset) => parseInt(hex.slice(offset, offset + 2), 16)) as RGB;
}

function luminance(color: RGB): number {
  const linear = color.map((channel) => {
    const value = channel / 255;
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  });
  return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
}

function ratio(a: number, b: number): number {
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

export function contrastRatio(a: string, b: string): number {
  return ratio(luminance(rgb(a)), luminance(rgb(b)));
}

/** Solid accent buttons always get the more readable of black and white. */
export function onColor(background: string): string {
  return contrastRatio(background, '#000000') >= contrastRatio(background, '#ffffff')
    ? '#000000'
    : '#ffffff';
}

function mix(start: RGB, end: RGB, amount: number): RGB {
  return start.map((channel, i) => channel + (end[i] - channel) * amount) as RGB;
}

function hex(color: RGB): string {
  return `#${color.map((channel) => Math.round(channel).toString(16).padStart(2, '0')).join('')}`;
}

/**
 * Keep decorative accents unchanged; soften only the secondary button stop if
 * its gradient would obscure the label. Sample the sRGB gradient, not just its
 * ends (the middle can be darker), with headroom above normal-text AA contrast.
 */
export function actionColors(brand: string, secondary: string) {
  const foreground = onColor(brand);
  const textLuminance = luminance(rgb(foreground));
  const start = rgb(brand);
  for (let step = 10; step > 0; step--) {
    const end = hex(mix(start, rgb(secondary), step / 10));
    const endRgb = rgb(end);
    if (
      Array.from({ length: 33 }, (_, i) =>
        ratio(luminance(mix(start, endRgb, i / 32)), textLuminance)
      ).every((contrast) => contrast >= 4.6)
    ) {
      return { start: brand, end, foreground };
    }
  }
  return { start: brand, end: brand, foreground };
}
