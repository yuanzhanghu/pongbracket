import { Button } from '@mantine/core';
import { IconStar, IconStarFilled } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';

import { getFollowedTournaments } from '@services/adapter';
import { tokenPresent } from '@services/local_storage';
import { addFavoriteTournament, removeFavoriteTournament } from '@services/tournament';

/**
 * Star toggle on a tournament's results page. Lets a logged-in viewer follow/unfollow
 * any tournament they can see — it then appears under the home page's
 * 我关注的比赛 tab. Hidden for anonymous visitors (they must log in to follow).
 */
export function FavoriteButton({ tournamentId }: { tournamentId: number }) {
  const { t } = useTranslation();
  if (!tokenPresent()) {
    return null;
  }

  const swrFollowed = getFollowedTournaments();
  const followed = swrFollowed.data != null ? swrFollowed.data.data : [];
  const isFavorited = followed.some((t: any) => t.id === tournamentId);

  return (
    <Button
      variant={isFavorited ? 'filled' : 'outline'}
      color="yellow"
      leftSection={isFavorited ? <IconStarFilled size={18} /> : <IconStar size={18} />}
      onClick={async () => {
        if (isFavorited) {
          await removeFavoriteTournament(tournamentId);
        } else {
          await addFavoriteTournament(tournamentId);
        }
        await swrFollowed.mutate();
      }}
    >
      {isFavorited ? t('following_button') : t('follow_button')}
    </Button>
  );
}
