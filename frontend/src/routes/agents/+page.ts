import { redirect } from '@sveltejs/kit';
import { resolve } from '$app/paths';
import type { PageLoad } from './$types';

// Preserve bookmarks without retaining a second, mutable workflow editor.
export const load: PageLoad = ({ url }) => {
  const team = url.searchParams.get('team');
  const validId = team && /^[0-9a-f]{8}-[0-9a-f-]{27}$/i.test(team);
  redirect(307, validId ? resolve('/teams/[id]', { id: team }) : resolve('/teams'));
};
