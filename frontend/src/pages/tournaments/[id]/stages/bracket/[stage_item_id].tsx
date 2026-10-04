import { Title } from '@mantine/core';
import { SWRResponse } from 'swr';

import { EliminationBracket } from '@components/brackets/brackets';
import {
  getStageItemIdFromRouter,
  getTournamentIdFromRouter,
  responseIsValid,
} from '@components/utils/util';
import NotFoundTitle from '@pages/404';
import TournamentLayout from '@pages/tournaments/_tournament_layout';
import { checkForAuthError, getStages, getTournamentById } from '@services/adapter';
import { getStageItemLookup } from '@services/lookups';

export default function StageItemBracketPage() {
  const { id, tournamentData } = getTournamentIdFromRouter();
  const stageItemId = getStageItemIdFromRouter();

  const swrTournamentResponse = getTournamentById(tournamentData.id);
  checkForAuthError(swrTournamentResponse);
  const swrStagesResponse: SWRResponse = getStages(id);
  const tournamentDataFull = swrTournamentResponse.data?.data;

  const stageItem =
    responseIsValid(swrStagesResponse) && stageItemId != null
      ? getStageItemLookup(swrStagesResponse)[stageItemId]
      : null;

  if (!swrTournamentResponse.isLoading && tournamentDataFull == null) {
    return <NotFoundTitle />;
  }
  if (tournamentDataFull == null) {
    return null;
  }

  return (
    <TournamentLayout tournament_id={tournamentData.id}>
      <Title mb="1rem">{stageItem != null ? stageItem.name : ''}</Title>
      {stageItem != null && (
        <EliminationBracket
          stageItem={stageItem}
          tournamentData={tournamentDataFull}
          swrStagesResponse={swrStagesResponse}
        />
      )}
    </TournamentLayout>
  );
}
