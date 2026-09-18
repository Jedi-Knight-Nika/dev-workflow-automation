export const money = (value: number) => `$${value.toFixed(4)}`;
export const duration = (value: number) => `${(value / 3600000).toFixed(2)}h`;
export const title = (value: string) => value.replaceAll('_', ' ').toLowerCase();
export function localDate(date: Date): string {
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, -1);
}
