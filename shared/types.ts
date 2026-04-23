export type ProviderKind = 'openai_compatible';

export type EntryTriggerMode = 'always' | 'keyword';

export type WorldBookInsertionPosition =
  | 'before_char'
  | 'after_char'
  | 'before_example'
  | 'after_example'
  | 'top_an'
  | 'bottom_an'
  | 'at_depth';

export interface ProviderConfig {
  provider: ProviderKind;
  baseUrl: string;
  apiKey: string;
  model: string;
  timeoutMs: number;
  temperature: number;
  enabled: boolean;
  prefixPrompt?: string;
  prefixPromptMode?: 'custom' | 'builtin';
  builtinPrefixPromptModel?: string;
  extraHeaders?: Record<string, string>;
}

export interface AppSettings {
  textProvider: ProviderConfig;
  imageProvider: ProviderConfig;
  exportDirectory: string;
  recentDirectory: string;
}

export interface WorldBookAdvancedOptions {
  insertionOrder: number;
  triggerProbability: number;
  insertionPosition: WorldBookInsertionPosition;
  depth: number;
}

export interface CharacterDefinition {
  id: string;
  enabled: boolean;
  triggerMode: EntryTriggerMode;
  name: string;
  triggerKeywords: string[];
  age: string;
  appearance: string;
  personality: string;
  speakingStyle: string;
  speakingExample: string;
  background: string;
  advanced: WorldBookAdvancedOptions;
}

export interface WorldBookEntry {
  id: string;
  enabled: boolean;
  triggerMode: EntryTriggerMode;
  title: string;
  keywords: string[];
  content: string;
  advanced: WorldBookAdvancedOptions;
}

export interface CardMeta {
  name: string;
  description: string;
}

export interface OpeningInfo {
  id: string;
  title: string;
  greeting: string;
  scenario: string;
  exampleDialogue: string;
  firstMessage: string;
}

export interface TimelineNode {
  id: string;
  parentId: string;
  title: string;
  timePoint: string;
  trigger: string;
  event: string;
  objective: string;
  conflict: string;
  outcome: string;
  nextHook: string;
}

export interface TimelineInfo {
  title: string;
  enabled: boolean;
  triggerMode: 'always';
  keywords: string[];
  nodes: TimelineNode[];
}

export interface IllustrationInfo {
  originalImagePath: string;
  generatedImagePath: string;
  exportImagePath: string;
  promptSnapshot: string;
  negativePrompt: string;
  stylePrompt: string;
}

export interface CharacterDraft {
  id: string;
  version: number;
  sourceType: 'roleplaycard' | 'external';
  createdAt: string;
  updatedAt: string;
  card: CardMeta;
  characters: CharacterDefinition[];
  openings: OpeningInfo[];
  opening?: OpeningInfo;
  worldBook: {
    entries: WorldBookEntry[];
  };
  timeline: TimelineInfo;
  illustration: IllustrationInfo;
}

export interface DraftSummary {
  id: string;
  name: string;
  updatedAt: string;
}

export interface TaskResult<T> {
  success: boolean;
  error_code: string | null;
  message: string;
  data: T | null;
}

export interface GenerateFieldRequest {
  field: string;
  mode: 'generate' | 'rewrite';
  draft: CharacterDraft;
  userInput: string;
  settings?: AppSettings;
}

export interface GenerateFieldResponse {
  field: string;
  result: string;
  promptPreview: string;
}

export interface ImagePromptResponse {
  prompt: string;
  negativePrompt: string;
}

export interface GenerateImageRequest {
  draft: CharacterDraft;
  prompt: string;
  negativePrompt: string;
  settings?: AppSettings;
}

export interface GenerateImageResponse {
  imagePath: string;
  prompt: string;
}

export interface GenerateCardFromStoryRequest {
  draft: CharacterDraft;
  storyText: string;
  settings?: AppSettings;
}

export interface GenerateCardFromStoryResponse {
  draft: CharacterDraft;
  raw: string;
}

export interface ExportCharacterCardRequest {
  draft: CharacterDraft;
  imagePath: string;
}

export interface ExportCharacterCardResponse {
  filename: string;
  imageBase64: string;
}

export interface ImportCharacterCardRequest {
  inputPath: string;
}

export interface ImportCharacterCardResponse {
  draft: CharacterDraft;
  sourcePath: string;
  sourceType: 'roleplaycard' | 'external';
}

export interface UploadImageResponse {
  path: string;
}

export interface ProviderValidationResult {
  provider: ProviderKind;
  ok: boolean;
  detail: string;
}

export interface BuiltinPrefixPromptOption {
  model: string;
  filename: string;
}

export interface BuiltinPrefixPromptListResponse {
  directory: string;
  items: BuiltinPrefixPromptOption[];
}
