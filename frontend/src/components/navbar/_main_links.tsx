import { Center, Divider, Group, Tooltip, UnstyledButton } from '@mantine/core';
import {
  Icon,
  IconBrackets,
  IconCalendar,
  IconChartLine,
  IconHome,
  IconScoreboard,
  IconSettings,
  IconTrophy,
  IconUser,
  IconUsers,
} from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { useLocation } from 'react-router';

import PreloadLink from '@components/utils/link';
import { useTeamNamingContext } from '@components/utils/team_naming';
import { capitalize } from '@components/utils/util';
import { getUser } from '@services/adapter';
import classes from './_main_links.module.css';

interface MainLinkProps {
  icon: Icon;
  label: string;
  link: string;
  links?: MainLinkProps[] | null;
}

function MainLinkMobile({ item, pathName }: { item: MainLinkProps; pathName: String }) {
  return (
    <>
      <UnstyledButton
        hiddenFrom="sm"
        component={PreloadLink}
        href={item.link}
        className={classes.mobileLink}
        style={{ width: '100%' }}
        data-active={pathName === item.link || undefined}
      >
        <Group className={classes.mobileLinkGroup}>
          <item.icon stroke={1.5} />
          {/* A <p> here would add its 1rem default margins to every row. */}
          <span style={{ marginLeft: '0.5rem' }}>{item.label}</span>
        </Group>
        <Divider />
      </UnstyledButton>
    </>
  );
}

function MainLink({ item, pathName }: { item: MainLinkProps; pathName: String }) {
  return (
    <>
      <Tooltip position="right" label={item.label} transitionProps={{ duration: 0 }}>
        <UnstyledButton
          visibleFrom="sm"
          component={PreloadLink}
          href={item.link}
          className={classes.link}
          data-active={pathName.startsWith(item.link) || undefined}
        >
          <item.icon stroke={1.5} />
        </UnstyledButton>
      </Tooltip>
      <MainLinkMobile item={item} pathName={pathName} />
    </>
  );
}

export function getBaseLinksDict() {
  const { t } = useTranslation();
  const swrUser = getUser();
  const isAdmin = swrUser.data?.data?.is_admin === true;

  return [
    // Clubs are implicit (one hidden personal club per account); no club UI.
    { link: '/', label: capitalize(t('tournaments_title')), links: [], icon: IconHome },
    {
      link: '/my-rating',
      label: t('my_rating_title'),
      links: [],
      icon: IconChartLine,
    },
    {
      link: '/user',
      label: t('user_title'),
      links: [],
      icon: IconUser,
    },
    ...(isAdmin
      ? [{ link: '/admin', label: t('admin_panel_title'), links: [], icon: IconSettings }]
      : []),
  ];
}

export function getBaseLinks() {
  const location = useLocation();
  const pathName = location.pathname.replace(/\/+$/, '');
  return getBaseLinksDict()
    .filter((link) => link.links.length < 1)
    .map((link) => <MainLinkMobile key={link.label} item={link} pathName={pathName} />);
}

export function TournamentLinks({ tournament_id }: any) {
  const location = useLocation();
  const { t } = useTranslation();
  const teamContext = useTeamNamingContext(tournament_id);
  const tm_prefix = `/tournaments/${tournament_id}`;
  const pathName = location.pathname.replace('[id]', tournament_id).replace(/\/+$/, '');

  const data = [
    {
      icon: IconTrophy,
      label: capitalize(t('stage_title')),
      link: `${tm_prefix}/stages`,
    },
    {
      icon: IconUsers,
      label: capitalize(t('teams_title', { context: teamContext })),
      link: `${tm_prefix}/teams`,
    },
    {
      icon: IconCalendar,
      label: capitalize(t('planning_title')),
      link: `${tm_prefix}/schedule`,
    },
    {
      icon: IconBrackets,
      label: capitalize(t('results_title')),
      link: `${tm_prefix}/results`,
    },
    {
      icon: IconScoreboard,
      label: capitalize(t('scoring_settings_title')),
      link: `${tm_prefix}/rankings`,
    },
    {
      icon: IconSettings,
      label: capitalize(t('tournament_setting_title')),
      link: `${tm_prefix}/settings`,
    },
  ];

  const links = data.map((link) => <MainLink key={link.label} item={link} pathName={pathName} />);
  return (
    <>
      <Center hiddenFrom="sm">
        <h2>{capitalize(t('tournament_title'))}</h2>
      </Center>
      <Divider hiddenFrom="sm" />
      {links}
    </>
  );
}
