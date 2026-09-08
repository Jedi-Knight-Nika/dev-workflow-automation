import { t } from '$lib/i18n/index.svelte';

export const money = (value: string | number | null | undefined) =>
  value == null ? t('operations.unavailable') : `$${Number(value).toFixed(4)}`;
export const count = (value: number | null | undefined) =>
  value == null ? t('operations.unknownValue') : value.toLocaleString();
export const bytes = (value: number | null | undefined) =>
  value == null ? t('operations.unavailable') : `${(value / 1024 ** 3).toFixed(2)} GiB`;
export const duration = (value: number | null | undefined) =>
  value == null
    ? t('operations.unavailable')
    : value < 60
      ? `${value.toFixed(0)}s`
      : `${(value / 60).toFixed(1)}m`;
export const percent = (value: number | null | undefined) =>
  value == null ? t('operations.unavailable') : `${(value * 100).toFixed(1)}%`;
