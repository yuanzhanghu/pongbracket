import { Button, Grid, Select, Tabs } from '@mantine/core';
import { IconBook, IconStar, IconTrophy, IconUserPlus } from '@tabler/icons-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import TournamentsCardTable from '@components/card_tables/tournaments';
import TournamentModal from '@components/modals/tournament_modal';
import { guideIndexHref } from '@components/utils/guide';
import PreloadLink from '@components/utils/link';
import { TournamentFilter } from '@components/utils/tournament';
import {
  checkForAuthError,
  getFollowedTournaments,
  getJoinableTournaments,
  getTournaments,
} from '@services/adapter';
import { tokenPresent } from '@services/local_storage';
import LandingPage from './_landing';
import Layout from './_layout';
import classes from './index.module.css';

export default function HomePage() {
  // Anonymous visitors get the public landing page; logged-in users get their
  // tournament tabs. No redirect to /login from the home page.
  if (!tokenPresent()) {
    return <LandingPage />;
  }
  return <TournamentsHome />;
}

function CreatedTab() {
  const { t, i18n } = useTranslation();
  // Default to ALL so archived tournaments stay visible (cards carry an
  // 已归档 badge to tell them apart).
  const [filter, setFilter] = useState<TournamentFilter>('ALL');
  const swrTournamentsResponse = getTournaments(filter);
  checkForAuthError(swrTournamentsResponse);

  return (
    <>
      <Grid justify="flex-end" mb="md">
        <Grid.Col span="content" className={classes.fullWithMobile}>
          <Select
            size="md"
            data={[
              { label: t('status_filter_all'), value: 'ALL' },
              { label: t('status_filter_archived'), value: 'ARCHIVED' },
              { label: t('status_filter_open'), value: 'OPEN' },
            ]}
            allowDeselect={false}
            value={filter}
            // @ts-ignore
            onChange={(f: TournamentFilter) => setFilter(f)}
          />
        </Grid.Col>
        <Grid.Col span="content" className={classes.fullWithMobile}>
          <Button
            component="a"
            href={guideIndexHref(i18n)}
            target="_blank"
            size="md"
            variant="outline"
            leftSection={<IconBook size={20} />}
          >
            {t('user_guide_title')}
          </Button>
        </Grid.Col>
        <Grid.Col span="content" className={classes.fullWithMobile}>
          <Button
            component={PreloadLink}
            href="/showcase"
            size="md"
            variant="outline"
            leftSection={<IconTrophy size={20} />}
          >
            {t('showcase_title')}
          </Button>
        </Grid.Col>
        <Grid.Col span="content" className={classes.fullWithMobile}>
          <TournamentModal swrTournamentsResponse={swrTournamentsResponse} />
        </Grid.Col>
      </Grid>
      <TournamentsCardTable swrTournamentsResponse={swrTournamentsResponse} linkTo="stages" />
    </>
  );
}

function FollowedTab() {
  const swrFollowed = getFollowedTournaments();
  checkForAuthError(swrFollowed);
  // Followed/joined tournaments open the read-only results (bracket/standings)
  // view — that's what a participant or spectator wants to see, not the organiser
  // stages page or the results page.
  return <TournamentsCardTable swrTournamentsResponse={swrFollowed} linkTo="results" />;
}

function JoinableTab() {
  const swrJoinable = getJoinableTournaments();
  checkForAuthError(swrJoinable);
  // Joinable tournaments open the results page — its 参赛 section is where the
  // user actually signs up.
  return <TournamentsCardTable swrTournamentsResponse={swrJoinable} linkTo="results" />;
}

function TournamentsHome() {
  const { t } = useTranslation();
  return (
    <Layout>
      <Tabs defaultValue="created">
        <Tabs.List mb="lg">
          <Tabs.Tab value="created" fz="lg" fw={600} leftSection={<IconTrophy size={20} />}>
            {t('created_tournaments_tab_title')}
          </Tabs.Tab>
          <Tabs.Tab value="followed" fz="lg" fw={600} leftSection={<IconStar size={20} />}>
            {t('followed_tournaments_tab_title')}
          </Tabs.Tab>
          <Tabs.Tab value="joinable" fz="lg" fw={600} leftSection={<IconUserPlus size={20} />}>
            {t('joinable_tournaments_tab_title')}
          </Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="created">
          <CreatedTab />
        </Tabs.Panel>
        <Tabs.Panel value="followed">
          <FollowedTab />
        </Tabs.Panel>
        <Tabs.Panel value="joinable">
          <JoinableTab />
        </Tabs.Panel>
      </Tabs>
    </Layout>
  );
}
