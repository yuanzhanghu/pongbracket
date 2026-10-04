import {
  Button,
  Card,
  Checkbox,
  Divider,
  Grid,
  Group,
  Image,
  Modal,
  NumberInput,
  SegmentedControl,
  Select,
  Stack,
  Text,
  UnstyledButton,
} from '@mantine/core';
import { UseFormReturnType, useForm } from '@mantine/form';
import { GoPlus } from '@react-icons/all-files/go/GoPlus';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { SWRResponse } from 'swr';

import { teamNamingContext } from '@components/utils/team_naming';
import { Translator } from '@components/utils/types';
import {
  StageItemInputOptionsResponse,
  StageItemWithRounds,
  StageWithStageItems,
  StagesWithStageItemsResponse,
  Tournament,
} from '@openapi';
import { getStageItemLookup, getTeamsLookup } from '@services/lookups';
import {
  createEliminationFromSources,
  createRoundRobinGroups,
  createStageItem,
} from '@services/stage_item';
import classes from './create_stage_item.module.css';

function StageSelectCard({
  title,
  description,
  image,
  selected,
  onClick,
}: {
  title: string;
  description: string;
  image: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <UnstyledButton onClick={onClick} w="100%">
      <Card
        shadow="sm"
        padding="lg"
        radius="lg"
        h="23rem"
        withBorder
        className={classes.socialLink}
        style={{ border: selected ? '3px solid var(--mantine-color-green-7)' : '' }}
      >
        <Card.Section style={{ backgroundColor: '#dde' }}>
          <Image src={image} h={212} style={{ padding: '1.5rem' }} fit="fill"></Image>
        </Card.Section>

        <Text fw={800} size="xl" mt="md" lineClamp={1}>
          {title}
        </Text>

        <Text mt="xs" c="dimmed" size="md" lineClamp={3}>
          {description}
        </Text>
      </Card>
    </UnstyledButton>
  );
}

export function CreateStagesFromTemplateButtons({
  selectedType,
  setSelectedType,
  teamContext,
  t,
}: {
  selectedType: 'ROUND_ROBIN' | 'SINGLE_ELIMINATION';
  setSelectedType: (type: 'ROUND_ROBIN' | 'SINGLE_ELIMINATION') => void;
  teamContext?: 'individual';
  t: Translator;
}) {
  return (
    <Grid grow>
      <Grid.Col span={{ base: 12, sm: 4 }}>
        <StageSelectCard
          title={t('round_robin_label')}
          description={t('round_robin_description', { context: teamContext })}
          image="/icons/group-stage-item.svg"
          selected={selectedType === 'ROUND_ROBIN'}
          onClick={() => {
            setSelectedType('ROUND_ROBIN');
          }}
        />
      </Grid.Col>
      <Grid.Col span={{ base: 12, sm: 4 }}>
        <StageSelectCard
          title={t('single_elimination_label')}
          description={t('single_elimination_description', { context: teamContext })}
          image="/icons/single-elimination-stage-item.svg"
          selected={selectedType === 'SINGLE_ELIMINATION'}
          onClick={() => {
            setSelectedType('SINGLE_ELIMINATION');
          }}
        />
      </Grid.Col>
    </Grid>
  );
}

function TeamCountSelectElimination({
  form,
  teamContext,
}: {
  form: UseFormReturnType<any>;
  teamContext?: 'individual';
}) {
  const { t } = useTranslation();
  const data = [
    { value: '2', label: '2' },
    { value: '4', label: '4' },
    { value: '8', label: '8' },
    { value: '16', label: '16' },
    { value: '32', label: '32' },
  ];
  return (
    <Select
      withAsterisk
      data={data}
      label={t('team_count_select_elimination_label', { context: teamContext })}
      placeholder={t('team_count_select_elimination_placeholder')}
      searchable
      limit={20}
      mt="1rem"
      maw="50%"
      {...form.getInputProps('team_count_elimination')}
    />
  );
}

function TeamCountInputRoundRobin({
  form,
  teamContext,
}: {
  form: UseFormReturnType<any>;
  teamContext?: 'individual';
}) {
  const { t } = useTranslation();
  return (
    <NumberInput
      withAsterisk
      label={t('team_count_input_round_robin_label', { context: teamContext })}
      placeholder=""
      mt="1rem"
      maw="50%"
      {...form.getInputProps('team_count_round_robin')}
    />
  );
}

function NumGroupsInputRoundRobin({
  form,
  teamContext,
}: {
  form: UseFormReturnType<any>;
  teamContext?: 'individual';
}) {
  const { t } = useTranslation();
  return (
    <NumberInput
      withAsterisk
      label={t('num_groups_label')}
      description={t('num_groups_description', { context: teamContext })}
      placeholder=""
      mt="1rem"
      maw="50%"
      min={1}
      {...form.getInputProps('num_groups')}
    />
  );
}

function GroupMethodInputRoundRobin({ form }: { form: UseFormReturnType<any> }) {
  const { t } = useTranslation();
  return (
    <Stack mt="1rem" gap="0.25rem">
      <Text fw={500} size="sm">
        {t('group_method_label')}
      </Text>
      <SegmentedControl
        maw="24rem"
        data={[
          { value: 'snake', label: t('group_method_snake') },
          { value: 'block', label: t('group_method_block') },
        ]}
        {...form.getInputProps('group_method')}
      />
    </Stack>
  );
}

type SourceSelections = Record<number, number>;
type TakeOption = 'top' | 'bottom';

function EliminationSourcePicker({
  sourceItems,
  sources,
  setSources,
  take,
  setTake,
}: {
  sourceItems: StageItemWithRounds[];
  sources: SourceSelections;
  setSources: (updater: (prev: SourceSelections) => SourceSelections) => void;
  take: TakeOption;
  setTake: (take: TakeOption) => void;
}) {
  const { t } = useTranslation();
  const total = Object.values(sources).reduce((sum, positions) => sum + (positions || 0), 0);

  return (
    <Stack mt="1rem" gap="0.5rem">
      <Text fw={600}>{t('elimination_sources_label')}</Text>
      <Text size="sm" c="dimmed">
        {t('elimination_sources_description')}
      </Text>
      <SegmentedControl
        maw="24rem"
        value={take}
        onChange={(value) => setTake(value as TakeOption)}
        data={[
          { value: 'top', label: t('take_top_option') },
          { value: 'bottom', label: t('take_bottom_option') },
        ]}
      />
      {sourceItems.map((item) => {
        const checked = sources[item.id] != null;
        return (
          <Group key={item.id} justify="space-between" maw="32rem" wrap="nowrap">
            <Checkbox
              label={item.name}
              checked={checked}
              onChange={(event) =>
                setSources((prev) => {
                  const next = { ...prev };
                  if (event.currentTarget.checked) next[item.id] = item.team_count;
                  else delete next[item.id];
                  return next;
                })
              }
            />
            <NumberInput
              w="9rem"
              min={1}
              max={item.team_count}
              label={t('positions_to_advance_label')}
              disabled={!checked}
              value={sources[item.id] ?? item.team_count}
              onChange={(value) =>
                setSources((prev) => ({ ...prev, [item.id]: Number(value) || 1 }))
              }
            />
          </Group>
        );
      })}
      <Text size="sm" mt="0.25rem">
        {`${t('qualifiers_total_label')}: ${total}`}
      </Text>
    </Stack>
  );
}

function TeamCountInput({
  form,
  sourceItems,
  sources,
  setSources,
  take,
  setTake,
  teamContext,
}: {
  form: UseFormReturnType<any>;
  sourceItems: StageItemWithRounds[];
  sources: SourceSelections;
  setSources: (updater: (prev: SourceSelections) => SourceSelections) => void;
  take: TakeOption;
  setTake: (take: TakeOption) => void;
  teamContext?: 'individual';
}) {
  if (form.values.type === 'SINGLE_ELIMINATION') {
    if (sourceItems.length > 0) {
      return (
        <EliminationSourcePicker
          sourceItems={sourceItems}
          sources={sources}
          setSources={setSources}
          take={take}
          setTake={setTake}
        />
      );
    }
    return <TeamCountSelectElimination form={form} teamContext={teamContext} />;
  }
  if (form.values.type === 'ROUND_ROBIN') {
    return (
      <>
        <TeamCountInputRoundRobin form={form} teamContext={teamContext} />
        <NumGroupsInputRoundRobin form={form} teamContext={teamContext} />
        <GroupMethodInputRoundRobin form={form} />
      </>
    );
  }

  return <TeamCountInputRoundRobin form={form} teamContext={teamContext} />;
}

function getTeamCount(values: any) {
  return Number(
    values.type === 'SINGLE_ELIMINATION'
      ? values.team_count_elimination
      : values.team_count_round_robin
  );
}

interface FormValues {
  type: 'ROUND_ROBIN' | 'SINGLE_ELIMINATION';
  num_groups: number;
  group_method: 'snake' | 'block';
  team_count_round_robin: number;
  team_count_elimination: number;
}
export function CreateStageItemModal({
  tournament,
  stage,
  swrStagesResponse,
  swrAvailableInputsResponse,
}: {
  tournament: Tournament;
  stage: StageWithStageItems;
  swrStagesResponse: SWRResponse<StagesWithStageItemsResponse>;
  swrAvailableInputsResponse: SWRResponse<StageItemInputOptionsResponse>;
}) {
  const { t } = useTranslation();
  const teamContext = teamNamingContext(tournament);
  const [opened, setOpened] = useState(false);
  const [sources, setSources] = useState<SourceSelections>({});
  const [take, setTake] = useState<TakeOption>('top');

  const form = useForm<FormValues>({
    initialValues: {
      type: 'ROUND_ROBIN',
      num_groups: 2,
      group_method: 'snake',
      team_count_round_robin: 4,
      team_count_elimination: 2,
    },
    validate: {
      num_groups: (value) => (value >= 1 ? null : t('at_least_one_group_validation')),
      team_count_round_robin: (value) =>
        value >= 2 ? null : t('at_least_two_team_validation', { context: teamContext }),
      team_count_elimination: (value) =>
        value >= 2 ? null : t('at_least_two_team_validation', { context: teamContext }),
    },
  });

  // Stage items from earlier stages can feed a knockout (groups -> elimination, or a
  // previous elimination -> the next one).
  const allStages = swrStagesResponse.data?.data ?? [];
  const currentStageIndex = allStages.findIndex((s) => s.id === stage.id);
  const sourceItems: StageItemWithRounds[] = allStages
    .slice(0, currentStageIndex < 0 ? 0 : currentStageIndex)
    .flatMap((s) => s.stage_items);

  // Default every source to "all positions advance" each time the modal opens.
  useEffect(() => {
    if (opened) {
      const initial: SourceSelections = {};
      sourceItems.forEach((item) => {
        initial[item.id] = item.team_count;
      });
      setSources(initial);
      setTake('top');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opened]);

  // TODO: Refactor lookups into one request.
  const teamsMap = getTeamsLookup(tournament != null ? tournament.id : -1);
  const stageItemMap = getStageItemLookup(swrStagesResponse);

  if (teamsMap == null || stageItemMap == null) {
    return null;
  }

  return (
    <>
      <Modal
        opened={opened}
        onClose={() => setOpened(false)}
        title={t('add_stage_item_modal_title')}
        size="60rem"
      >
        <form
          onSubmit={form.onSubmit(async (values) => {
            if (values.type === 'ROUND_ROBIN') {
              await createRoundRobinGroups(
                tournament.id,
                stage.id,
                values.num_groups,
                values.team_count_round_robin,
                values.group_method
              );
            } else if (values.type === 'SINGLE_ELIMINATION' && sourceItems.length > 0) {
              const selected = Object.entries(sources)
                .filter(([, positions]) => positions >= 1)
                .map(([stage_item_id, positions]) => ({
                  stage_item_id: Number(stage_item_id),
                  positions: Number(positions),
                }));
              await createEliminationFromSources(tournament.id, stage.id, null, selected, take);
            } else {
              await createStageItem(tournament.id, stage.id, values.type, getTeamCount(values));
            }
            await swrStagesResponse.mutate();
            await swrAvailableInputsResponse.mutate();
            setOpened(false);
          })}
        >
          <CreateStagesFromTemplateButtons
            t={t}
            selectedType={form.values.type}
            setSelectedType={(_type) => {
              form.setFieldValue('type', _type);
            }}
            teamContext={teamContext}
          />
          <Divider mt="1rem" />
          <TeamCountInput
            form={form}
            sourceItems={sourceItems}
            sources={sources}
            setSources={setSources}
            take={take}
            setTake={setTake}
            teamContext={teamContext}
          />

          <Button fullWidth mt="1.5rem" color="green" type="submit">
            {t('create_stage_item_button')}
          </Button>
        </form>
      </Modal>

      <Button
        variant="outline"
        color="green"
        size="xs"
        onClick={() => setOpened(true)}
        leftSection={<GoPlus size={24} />}
      >
        {t('add_stage_item_modal_title')}
      </Button>
    </>
  );
}
