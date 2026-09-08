export const money = (value: string | number | null | undefined) =>
  value == null ? 'Unavailable' : `$${Number(value).toFixed(4)}`;
export const count = (value: number | null | undefined) =>
  value == null ? 'Unknown' : value.toLocaleString();
export const bytes = (value: number | null | undefined) =>
  value == null ? 'Unavailable' : `${(value / 1024 ** 3).toFixed(2)} GiB`;
export const duration = (value: number | null | undefined) =>
  value == null
    ? 'Unavailable'
    : value < 60
      ? `${value.toFixed(0)}s`
      : `${(value / 60).toFixed(1)}m`;
export const percent = (value: number | null | undefined) =>
  value == null ? 'Unavailable' : `${(value * 100).toFixed(1)}%`;
