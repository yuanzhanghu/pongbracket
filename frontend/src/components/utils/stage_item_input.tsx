import {
  StageItemInputEmpty,
  StageItemInputFinal,
  StageItemInputOptionFinal,
  StageItemInputOptionTentative,
  StageItemInputTentative,
} from '@openapi';
import i18n from '../../../i18n';
import { assert_not_none } from './assert';

export type StageItemInput = StageItemInputTentative | StageItemInputFinal | StageItemInputEmpty;
export type StageItemInputOption = StageItemInputOptionTentative | StageItemInputOptionFinal;

export interface StageItemInputChoice {
  value: string;
  label: string;
  team_id: number | null;
  winner_from_stage_item_id: number | null;
  winner_position: number | null;
  already_taken: boolean;
}

export function formatStageItemInputTentative(
  stage_item_input: StageItemInputTentative | StageItemInputOptionTentative,
  stageItemsLookup: any
) {
  const position = assert_not_none(stage_item_input.winner_position);
  const stageItemName =
    stageItemsLookup[assert_not_none(stage_item_input.winner_from_stage_item_id)].name;
  return i18n.t('stage_item_input_position', { name: stageItemName, position });
}

export function formatStageItemInput(
  stage_item_input: StageItemInput | null,
  stageItemsLookup: any
) {
  if (stage_item_input == null) return null;
  if ('team' in stage_item_input) return stage_item_input.team.name;
  if (stage_item_input?.winner_from_stage_item_id != null) {
    return formatStageItemInputTentative(stage_item_input, stageItemsLookup);
  }
  return null;
}
