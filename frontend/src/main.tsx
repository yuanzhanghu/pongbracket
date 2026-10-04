import '@mantine/charts/styles.css';
import { MantineProvider, createTheme } from '@mantine/core';
import '@mantine/core/styles.css';
import '@mantine/dates/styles.css';
import '@mantine/dropzone/styles.css';
import { Notifications } from '@mantine/notifications';
import '@mantine/notifications/styles.css';
import '@mantine/spotlight/styles.css';
import { NuqsAdapter } from 'nuqs/adapters/react-router/v7';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { I18nextProvider } from 'react-i18next';
import { BrowserRouter, Route, Routes } from 'react-router';

import i18n from '../i18n';
import { BracketSpotlight } from './components/modals/spotlight';
import { DocumentHead, LocalizedDatesProvider } from './components/utils/localization';
import HomePage from './pages';
import NotFoundPage from './pages/404';
import AdminPage from './pages/admin';
import CreateAccountPage from './pages/create_account';
import CreateDemoAccountPage from './pages/demo';
import LoginPage from './pages/login';
import MyRatingPage from './pages/my_rating';
import PasswordResetPage from './pages/password_reset';
import LeaderboardPage from './pages/rating/[category_id]/leaderboard';
import ShowcasePage from './pages/showcase';
import RankingsPage from './pages/tournaments/[id]/rankings';
import ResultsPage from './pages/tournaments/[id]/results';
import SchedulePage from './pages/tournaments/[id]/schedule';
import SettingsPage from './pages/tournaments/[id]/settings';
import StagesPage from './pages/tournaments/[id]/stages';
import StageItemBracketPage from './pages/tournaments/[id]/stages/bracket/[stage_item_id]';
import TeamsPage from './pages/tournaments/[id]/teams';
import UserPage from './pages/user';

const theme = createTheme({
  colors: {
    dark: [
      '#C1C2C5',
      '#A6A7AB',
      '#909296',
      '#5c5f66',
      '#373A40',
      '#2C2E33',
      '#25262b',
      '#1A1B1E',
      '#141517',
      '#101113',
    ],
  },
});

function AnalyticsScript() {
  if (import.meta.env.VITE_ANALYTICS_SCRIPT_SRC == null) {
    return null;
  }

  var script = document.createElement('script');
  script.setAttribute('async', '');
  script.setAttribute('data-domain', import.meta.env.VITE_ANALYTICS_DATA_DOMAIN);
  script.setAttribute('data-website-id', import.meta.env.VITE_ANALYTICS_DATA_WEBSITE_ID);
  script.setAttribute('src', import.meta.env.VITE_ANALYTICS_SCRIPT_SRC);
  document.head.appendChild(script);
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <NuqsAdapter>
      <BrowserRouter>
        <I18nextProvider i18n={i18n}>
          <MantineProvider defaultColorScheme="auto" theme={theme}>
            <LocalizedDatesProvider>
              <DocumentHead />
              <BracketSpotlight />
              <Notifications />
              <Routes>
                <Route index element={<HomePage />} />
                <Route path="/login" element={<LoginPage />} />
                <Route path="/demo" element={<CreateDemoAccountPage />} />
                <Route path="/user" element={<UserPage />} />
                <Route path="/my-rating" element={<MyRatingPage />} />
                <Route path="/admin" element={<AdminPage />} />
                <Route path="/rating/:category_id/leaderboard" element={<LeaderboardPage />} />
                <Route path="/showcase" element={<ShowcasePage />} />
                <Route path="/password-reset" element={<PasswordResetPage />} />
                <Route path="/create-account" element={<CreateAccountPage />} />

                <Route path="/tournaments">
                  <Route path=":id">
                    <Route path="teams" element={<TeamsPage />} />
                    <Route path="schedule" element={<SchedulePage />} />
                    <Route path="rankings" element={<RankingsPage />} />
                    <Route path="settings" element={<SettingsPage />} />
                    <Route path="results" element={<ResultsPage />} />
                    <Route path="stages">
                      <Route index element={<StagesPage />} />
                      <Route path="bracket/:stage_item_id" element={<StageItemBracketPage />} />
                    </Route>
                  </Route>
                </Route>
                <Route path="*" element={<NotFoundPage />} />
              </Routes>
            </LocalizedDatesProvider>
          </MantineProvider>
        </I18nextProvider>
      </BrowserRouter>
    </NuqsAdapter>
  </StrictMode>
);

AnalyticsScript();
