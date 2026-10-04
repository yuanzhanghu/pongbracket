import {
  ActionIcon,
  Badge,
  Card,
  Group,
  Menu,
  NativeSelect,
  Stack,
  Text,
  Tooltip,
  useMantineTheme,
} from '@mantine/core';
import { AiFillWarning } from '@react-icons/all-files/ai/AiFillWarning';
import { IconDots, IconPencil, IconTournament, IconTrash } from '@tabler/icons-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { SWRResponse } from 'swr';

import CreateStageButton from '@components/buttons/create_stage';
import { CreateStageItemModal } from '@components/modals/create_stage_item';
import { UpdateStageModal } from '@components/modals/update_stage';
import { UpdateStageItemModal } from '@components/modals/update_stage_item';
import { assert_not_none } from '@components/utils/assert';
import RequestErrorAlert from '@components/utils/error_alert';
import PreloadLink from '@components/utils/link';
import {
  StageItemInput,
  StageItemInputChoice,
  StageItemInputOption,
  formatStageItemInputTentative,
} from '@components/utils/stage_item_input';
import {
  Ranking,
  StageItemInputOptionsResponse,
  StageItemWithRounds,
  StageRankingResponse,
  StageWithStageItems,
  StagesWithStageItemsResponse,
  Tournament,
} from '@openapi';
import { getStageItemLookup, getTeamsLookup } from '@services/lookups';
import { deleteStage } from '@services/stage';
import { deleteStageItem } from '@services/stage_item';
import { updateStageItemInput } from '@services/stage_item_input';

function StageItemInputComboBox({
  tournament,
  stageItemInput,
  current_key,
  availableInputs,
  swrAvailableInputsResponse,
  swrRankingsPerStageItemResponse,
  swrStagesResponse,
}: {
  tournament: Tournament;
  stageItemInput: StageItemInput;
  current_key: string | null;
  availableInputs: StageItemInputChoice[];
  swrAvailableInputsResponse: SWRResponse<StageItemInputOptionsResponse>;
  swrRankingsPerStageItemResponse: SWRResponse<StageRankingResponse>;
  swrStagesResponse: SWRResponse<StagesWithStageItemsResponse>;
}) {
  const { t } = useTranslation();
  const theme = useMantineTheme();

  // Once the stage is activated and a team has been resolved for this slot, show the
  // actual team name instead of the seed placeholder (e.g. "1st of zu1").
  const resolvedTeamName = (stageItemInput as { team?: { name?: string } })?.team?.name ?? null;

  // Options for this slot. Keep the currently-selected one even if it's flagged as taken.
  const data = availableInputs
    .filter((option) => !option.already_taken || option.value === current_key)
    .map((option) => ({
      value: option.value,
      label:
        option.value === current_key && resolvedTeamName
          ? resolvedTeamName
          : option.label || t('empty_slot'),
    }));

  const onChange = (value: string | null) => {
    const option = availableInputs.find((o) => o.value === value) || null;
    updateStageItemInput(
      tournament.id,
      stageItemInput.stage_item_id,
      stageItemInput.id,
      option?.team_id || null,
      option?.winner_position || null,
      option?.winner_from_stage_item_id || null
    ).then(() => {
      swrAvailableInputsResponse.mutate();
      swrStagesResponse.mutate();
      swrRankingsPerStageItemResponse.mutate();
    });
  };

  // Use a native <select>: the browser/OS renders the picker, so it works reliably on
  // every device (no floating dropdown that can mis-position or get hidden on mobile),
  // and behaves identically on desktop and mobile.
  return (
    <NativeSelect
      radius="0.5rem"
      data={data}
      value={current_key ?? 'null'}
      onChange={(event) => onChange(event.currentTarget.value)}
      leftSection={
        current_key == null ? <AiFillWarning size={18} color={theme.colors.orange[4]} /> : undefined
      }
    />
  );
}

export function getAvailableInputs(
  swrAvailableInputsResponse: SWRResponse<StageItemInputOptionsResponse>,
  teamsMap: any,
  stageItemMap: any
) {
  const getComboBoxOptionForStageItemInput = (option: StageItemInputOption) => {
    if ('winner_from_stage_item_id' in option) {
      option.winner_position = assert_not_none(option.winner_position);
      const stageItem = stageItemMap[option.winner_from_stage_item_id];

      if (stageItem == null) return null;
      return {
        value: `${option.winner_from_stage_item_id}_${option.winner_position}`,
        label: `${formatStageItemInputTentative(option, stageItemMap)}`,
        team_id: null,
        winner_from_stage_item_id: option.winner_from_stage_item_id,
        winner_position: option.winner_position,
        already_taken: option.already_taken,
      };
    }

    const team = teamsMap[option.team_id];
    if (team == null) return null;
    return {
      value: `${assert_not_none(option.team_id)}`,
      label: team.name,
      team_id: team.id,
      winner_from_stage_item_id: null,
      winner_position: null,
      already_taken: option.already_taken,
    };
  };
  return swrAvailableInputsResponse.data != undefined
    ? Object.keys(swrAvailableInputsResponse.data?.data).reduce((result: any, stage_id: string) => {
        const option = assert_not_none(swrAvailableInputsResponse.data?.data[stage_id]);
        result[stage_id] = option
          .map((opt: StageItemInputOption) => getComboBoxOptionForStageItemInput(opt))
          .filter((o: StageItemInputOption | null) => o != null);
        return result;
      }, {})
    : {};
}

function StageItemInputSection({
  tournament,
  stageItemInput,
  currentOptionValue,
  lastInList,
  availableInputs,
  swrAvailableInputsResponse,
  swrStagesResponse,
  swrRankingsPerStageItemResponse,
}: {
  tournament: Tournament;
  stageItemInput: StageItemInput;
  currentOptionValue: string | null;
  lastInList: boolean;
  availableInputs: StageItemInputChoice[];
  swrAvailableInputsResponse: SWRResponse<StageItemInputOptionsResponse>;
  swrStagesResponse: SWRResponse<StagesWithStageItemsResponse>;
  swrRankingsPerStageItemResponse: SWRResponse<StageRankingResponse>;
}) {
  const opts = lastInList ? { pt: 'xs', mb: '-0.5rem' } : { py: 'xs', withBorder: true };

  return (
    <Card.Section inheritPadding {...opts}>
      <StageItemInputComboBox
        tournament={tournament}
        stageItemInput={stageItemInput}
        current_key={currentOptionValue}
        availableInputs={availableInputs}
        swrAvailableInputsResponse={swrAvailableInputsResponse}
        swrRankingsPerStageItemResponse={swrRankingsPerStageItemResponse}
        swrStagesResponse={swrStagesResponse}
      />
    </Card.Section>
  );
}

function StageItemRow({
  tournament,
  stageItem,
  swrStagesResponse,
  availableInputs,
  rankings,
  swrAvailableInputsResponse,
  swrRankingsPerStageItemResponse,
}: {
  tournament: Tournament;
  stageItem: StageItemWithRounds;
  swrStagesResponse: SWRResponse<StagesWithStageItemsResponse>;
  availableInputs: StageItemInputChoice[];
  rankings: Ranking[];
  swrAvailableInputsResponse: SWRResponse<StageItemInputOptionsResponse>;
  swrRankingsPerStageItemResponse: SWRResponse<StageRankingResponse>;
}) {
  const { t } = useTranslation();
  const [opened, setOpened] = useState(false);

  const inputs = stageItem.inputs
    .sort((i1, i2) => (i1.slot > i2.slot ? 1 : -1))
    .map((input, i) => {
      let currentOptionValue = null;
      if (input.winner_from_stage_item_id != null) {
        currentOptionValue = `${input.winner_from_stage_item_id}_${input.winner_position}`;
      } else if (input.team_id != null) {
        currentOptionValue = `${input.team_id}`;
      }

      return (
        <StageItemInputSection
          key={i}
          tournament={tournament}
          stageItemInput={input}
          currentOptionValue={currentOptionValue}
          availableInputs={availableInputs}
          lastInList={i === stageItem.inputs.length - 1}
          swrAvailableInputsResponse={swrAvailableInputsResponse}
          swrStagesResponse={swrStagesResponse}
          swrRankingsPerStageItemResponse={swrRankingsPerStageItemResponse}
        />
      );
    });

  return (
    <Card withBorder shadow="sm" radius="md">
      <Card.Section withBorder inheritPadding py="xs" color="dimmed">
        <Group justify="space-between">
          <Text fw={800}>{stageItem.name}</Text>
          <UpdateStageItemModal
            swrStagesResponse={swrStagesResponse}
            stageItem={stageItem}
            tournament={tournament}
            opened={opened}
            setOpened={setOpened}
            rankings={rankings}
          />
          <Group gap="0rem">
            {stageItem.type === 'SINGLE_ELIMINATION' ? (
              <Tooltip label={t('view_bracket_button')}>
                <ActionIcon
                  variant="transparent"
                  color="gray"
                  component={PreloadLink}
                  href={`/tournaments/${tournament.id}/stages/bracket/${stageItem.id}`}
                >
                  <IconTournament size="1.25rem" />
                </ActionIcon>
              </Tooltip>
            ) : null}
            <Menu withinPortal position="bottom-end" shadow="sm">
              <Menu.Target>
                <ActionIcon variant="transparent" color="gray">
                  <IconDots size="1.25rem" />
                </ActionIcon>
              </Menu.Target>

              <Menu.Dropdown>
                <Menu.Item
                  leftSection={<IconPencil size="1.5rem" />}
                  onClick={() => {
                    setOpened(true);
                  }}
                >
                  {t('edit_stage_item_label')}
                </Menu.Item>
                <Menu.Item
                  leftSection={<IconTrash size="1.5rem" />}
                  onClick={async () => {
                    await deleteStageItem(tournament.id, stageItem.id);
                    await swrStagesResponse.mutate();
                    await swrAvailableInputsResponse.mutate();
                  }}
                  color="red"
                >
                  {t('delete_button')}
                </Menu.Item>
              </Menu.Dropdown>
            </Menu>
          </Group>
        </Group>
      </Card.Section>
      {inputs}
    </Card>
  );
}

function StageColumn({
  tournament,
  stage,
  swrStagesResponse,
  swrAvailableInputsResponse,
  swrRankingsPerStageItemResponse,
  rankings,
}: {
  tournament: Tournament;
  stage: StageWithStageItems;
  swrStagesResponse: SWRResponse<StagesWithStageItemsResponse>;
  swrAvailableInputsResponse: SWRResponse<StageItemInputOptionsResponse>;
  swrRankingsPerStageItemResponse: SWRResponse<StageRankingResponse>;
  rankings: Ranking[];
}) {
  const { t } = useTranslation();
  const [opened, setOpened] = useState(false);
  const teamsMap = getTeamsLookup(tournament != null ? tournament.id : -1);
  const stageItemsLookup = getStageItemLookup(swrStagesResponse);

  if (teamsMap == null) {
    return null;
  }

  const availableInputs =
    getAvailableInputs(swrAvailableInputsResponse, teamsMap, stageItemsLookup)[stage.id] || [];
  availableInputs.push({
    value: 'null',
    label: null,
    team_id: null,
    winner_from_stage_item_id: null,
    winner_position: null,
    already_taken: false,
  });

  const rows = stage.stage_items
    .sort((i1: StageItemWithRounds, i2: StageItemWithRounds) => (i1.id > i2.id ? 1 : -1))
    .sort((i1: StageItemWithRounds, i2: StageItemWithRounds) => (i1.name > i2.name ? 1 : -1))
    .map((stageItem: StageItemWithRounds) => (
      <StageItemRow
        key={stageItem.id}
        tournament={tournament}
        stageItem={stageItem}
        swrStagesResponse={swrStagesResponse}
        availableInputs={availableInputs}
        swrAvailableInputsResponse={swrAvailableInputsResponse}
        swrRankingsPerStageItemResponse={swrRankingsPerStageItemResponse}
        rankings={rankings}
      />
    ));

  return (
    <Stack miw="24rem" align="top" key={stage.id}>
      <UpdateStageModal
        swrStagesResponse={swrStagesResponse}
        stage={stage}
        tournament={tournament}
        opened={opened}
        setOpened={setOpened}
      />
      <Group justify="space-between">
        <Group>
          {`${t('stage_name_prefix')}${stage.name}`}
          {stage.is_active ? <Badge color="green">{t('active_badge_label')}</Badge> : null}
        </Group>
        <Menu withinPortal position="bottom-end" shadow="sm">
          <Menu.Target>
            <ActionIcon variant="transparent" color="gray">
              <IconDots size="1.25rem" />
            </ActionIcon>
          </Menu.Target>

          <Menu.Dropdown>
            <Menu.Item
              leftSection={<IconPencil size="1.5rem" />}
              onClick={() => {
                setOpened(true);
              }}
            >
              {t('edit_stage_label')}
            </Menu.Item>
            <Menu.Item
              leftSection={<IconTrash size="1.5rem" />}
              onClick={async () => {
                await deleteStage(tournament.id, stage.id);
                await swrStagesResponse.mutate();
                await swrAvailableInputsResponse.mutate();
              }}
              color="red"
            >
              {t('delete_button')}
            </Menu.Item>
          </Menu.Dropdown>
        </Menu>
      </Group>
      {rows}
      <CreateStageItemModal
        key={-1}
        tournament={tournament}
        stage={stage}
        swrStagesResponse={swrStagesResponse}
        swrAvailableInputsResponse={swrAvailableInputsResponse}
      />
    </Stack>
  );
}

export default function Builder({
  tournament,
  swrStagesResponse,
  swrAvailableInputsResponse,
  swrRankingsPerStageItemResponse,
  rankings,
}: {
  tournament: Tournament;
  swrStagesResponse: SWRResponse<StagesWithStageItemsResponse>;
  swrAvailableInputsResponse: SWRResponse<StageItemInputOptionsResponse>;
  swrRankingsPerStageItemResponse: SWRResponse<StageRankingResponse>;
  rankings: Ranking[];
}) {
  const stages: StageWithStageItems[] =
    swrStagesResponse.data != null ? swrStagesResponse.data.data : [];

  if (swrStagesResponse.error) return <RequestErrorAlert error={swrStagesResponse.error} />;
  if (swrAvailableInputsResponse.error) {
    return <RequestErrorAlert error={swrAvailableInputsResponse.error} />;
  }

  const cols = stages
    .sort((s1: StageWithStageItems, s2: StageWithStageItems) => (s1.id > s2.id ? 1 : -1))
    .map((stage) => (
      <StageColumn
        key={stage.id}
        tournament={tournament}
        swrStagesResponse={swrStagesResponse}
        swrAvailableInputsResponse={swrAvailableInputsResponse}
        swrRankingsPerStageItemResponse={swrRankingsPerStageItemResponse}
        stage={stage}
        rankings={rankings}
      />
    ));

  const button = (
    <Stack miw="24rem" align="top" key={-1}>
      <h4 style={{ marginTop: '0rem' }}>
        <CreateStageButton
          tournament={tournament}
          swrStagesResponse={swrStagesResponse}
          swrAvailableInputsResponse={swrAvailableInputsResponse}
          swrRankingsPerStageItemResponse={swrRankingsPerStageItemResponse}
        />
      </h4>
    </Stack>
  );
  return cols.concat([button]);
}
