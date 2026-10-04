import { Text } from '@mantine/core';
import { AiOutlineHourglass } from '@react-icons/all-files/ai/AiOutlineHourglass';
import { useTranslation } from 'react-i18next';
import { SWRResponse } from 'swr';

import { NoContent } from '@components/no_content/empty_table_info';
import { StandingsTableForStageItem } from '@components/tables/standings';
import { responseIsValid } from '@components/utils/util';
import { StagesWithStageItemsResponse } from '@openapi';
import { getStageItemLookup, getStageItemTeamsLookup } from '@services/lookups';

/** One standings table per stage item, ordered by stage item name. */
export function StandingsContent({
  swrStagesResponse,
  fontSizeInPixels,
  maxTeamsToDisplay,
  teamContext,
}: {
  swrStagesResponse: SWRResponse<StagesWithStageItemsResponse>;
  fontSizeInPixels: number;
  maxTeamsToDisplay: number;
  teamContext?: 'individual';
}) {
  const { t } = useTranslation();

  const stageItemsLookup = getStageItemLookup(swrStagesResponse);
  const stageItemTeamLookup = responseIsValid(swrStagesResponse)
    ? getStageItemTeamsLookup(swrStagesResponse)
    : {};

  const rows = Object.keys(stageItemTeamLookup)
    .filter((stageItemId) => stageItemsLookup[stageItemId] != null)
    .sort((si1: any, si2: any) =>
      stageItemsLookup[si1].name > stageItemsLookup[si2].name ? 1 : -1
    )
    .map((stageItemId) => (
      <div key={stageItemId}>
        <Text size="xl" mt="md" mb="xs" inherit>
          {stageItemsLookup[stageItemId].name}
        </Text>
        <StandingsTableForStageItem
          teams_with_inputs={stageItemTeamLookup[stageItemId]}
          stageItem={stageItemsLookup[stageItemId]}
          stageItemsLookup={stageItemsLookup}
          fontSizeInPixels={fontSizeInPixels}
          maxTeamsToDisplay={maxTeamsToDisplay}
          teamContext={teamContext}
        />
      </div>
    ));

  if (rows.length < 1) {
    return (
      <NoContent
        title={t('no_entity_found_title', {
          entity: t('teams_title', { context: teamContext }),
        })}
        description=""
        icon={<AiOutlineHourglass />}
      />
    );
  }
  return rows;
}
