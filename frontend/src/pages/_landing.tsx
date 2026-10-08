import {
  Anchor,
  Box,
  Button,
  Card,
  Container,
  Group,
  Image,
  SimpleGrid,
  Stack,
  Text,
  ThemeIcon,
  Title,
} from '@mantine/core';
import {
  IconBinaryTree,
  IconBook,
  IconBrandGithub,
  IconCalendar,
  IconDeviceTv,
  IconListNumbers,
  IconScoreboard,
  IconSitemap,
} from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';

import { guideIndexHref, guideShot } from '@components/utils/guide';
import LanguageSwitcher from '@components/utils/language_switcher';

export default function LandingPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();

  const features = [
    {
      icon: IconSitemap,
      title: t('landing_feature_formats_title'),
      desc: t('landing_feature_formats_desc'),
    },
    {
      icon: IconCalendar,
      title: t('landing_feature_schedule_title'),
      desc: t('landing_feature_schedule_desc'),
    },
    {
      icon: IconScoreboard,
      title: t('landing_feature_scoring_title'),
      desc: t('landing_feature_scoring_desc'),
    },
    {
      icon: IconListNumbers,
      title: t('landing_feature_rankings_title'),
      desc: t('landing_feature_rankings_desc'),
    },
    {
      icon: IconBinaryTree,
      title: t('landing_feature_bracket_title'),
      desc: t('landing_feature_bracket_desc'),
    },
    {
      icon: IconDeviceTv,
      title: t('landing_feature_dashboard_title'),
      desc: t('landing_feature_dashboard_desc'),
    },
  ];

  // Screenshots of the UI in the active language (i18n comes from
  // useTranslation, so switching language re-renders these).
  const shots = [
    { src: guideShot('stages', i18n), caption: t('landing_shot_stages') },
    { src: guideShot('schedule', i18n), caption: t('landing_shot_schedule') },
    { src: guideShot('rankings', i18n), caption: t('landing_shot_rankings') },
    { src: guideShot('bracket', i18n), caption: t('landing_shot_bracket') },
  ];

  // Shown both in the top-left corner and in the footer.
  const sourceLink = (
    <Anchor
      href="https://github.com/yuanzhanghu/pongbracket"
      target="_blank"
      rel="noopener noreferrer"
      c="dimmed"
      fz="sm"
    >
      <Group gap={6}>
        <IconBrandGithub size={18} />
        {t('landing_source_code')}
      </Group>
    </Anchor>
  );

  return (
    <Container size="lg" px="xs">
      <Group justify="space-between" mt="xs">
        {sourceLink}
        <LanguageSwitcher />
      </Group>

      {/* Hero */}
      <Stack align="center" gap="md" mt={24} mb={56} ta="center">
        <Title order={1} fz={{ base: 32, sm: 44 }} maw={760}>
          <Text inherit component="span" variant="gradient" gradient={{ from: 'blue', to: 'cyan' }}>
            {t('landing_title')}
          </Text>
        </Title>
        <Text c="dimmed" fz={{ base: 'md', sm: 'lg' }} maw={680}>
          {t('landing_subtitle')}
        </Text>
        <Group justify="center" mt="sm">
          <Button size="md" onClick={() => navigate('/login')}>
            {t('sign_in_title')}
          </Button>
          <Button
            size="md"
            variant="outline"
            leftSection={<IconBook size={20} />}
            component="a"
            href={guideIndexHref(i18n)}
            target="_blank"
          >
            {t('user_guide_title')}
          </Button>
          <Button size="md" variant="subtle" onClick={() => navigate('/create-account')}>
            {t('create_account_button')}
          </Button>
          <Button size="md" variant="subtle" onClick={() => navigate('/showcase')}>
            {t('showcase_title')}
          </Button>
        </Group>
      </Stack>

      {/* Features */}
      <Title order={2} ta="center" mb="xl">
        {t('landing_features_title')}
      </Title>
      <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }} spacing="lg" mb={64}>
        {features.map((f) => (
          <Card key={f.title} withBorder radius="md" padding="lg">
            <ThemeIcon size={48} radius="md" variant="light" color="blue">
              <f.icon size={28} />
            </ThemeIcon>
            <Text fw={700} fz="lg" mt="md">
              {f.title}
            </Text>
            <Text c="dimmed" fz="sm" mt={4}>
              {f.desc}
            </Text>
          </Card>
        ))}
      </SimpleGrid>

      {/* Screenshots */}
      <Title order={2} ta="center" mb="xl">
        {t('landing_screenshots_title')}
      </Title>
      <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="lg" mb={64}>
        {shots.map((s) => (
          <Card key={s.src} withBorder radius="md" padding="sm">
            <Card.Section>
              <Image src={s.src} alt={s.caption} fit="contain" />
            </Card.Section>
            <Text ta="center" c="dimmed" fz="sm" mt="sm">
              {s.caption}
            </Text>
          </Card>
        ))}
      </SimpleGrid>

      {/* Bottom CTA */}
      <Box ta="center" mb={64}>
        <Button size="lg" onClick={() => navigate('/login')}>
          {t('sign_in_title')}
        </Button>
      </Box>

      {/* Footer */}
      <Group justify="center" mb="xl">
        {sourceLink}
      </Group>
    </Container>
  );
}
