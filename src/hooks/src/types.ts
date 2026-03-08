/**
 * TypeScript type definitions for Academic Writer hooks
 * Based on Claude Code hook protocol (CC 2.1.69+)
 */

export type HookEvent =
  | 'SessionStart'
  | 'SessionEnd'
  | 'PreToolUse'
  | 'PostToolUse'
  | 'UserPromptSubmit'
  | 'Stop';

export interface HookInput {
  hook_event?: HookEvent;
  tool_name: string;
  session_id: string;
  tool_input: Record<string, unknown>;
  tool_output?: unknown;
  project_dir?: string;
  plugin_root?: string;
  prompt?: string;
}

export interface HookResult {
  continue: boolean;
  suppressOutput?: boolean;
  systemMessage?: string;
}

export interface ProfileData {
  fieldOfStudy: string;
  citationStyle: string;
  targetLanguage: string;
  styleFingerprint?: StyleFingerprint;
  tools?: Record<string, ToolConfig>;
  articleStructure?: ArticleStructure;
  outputFormatPreferences?: OutputFormatPreferences;
}

export interface ToolConfig {
  enabled: boolean;
  path?: string;
}

export interface StyleFingerprint {
  sentenceLevel?: SentenceLevel;
  vocabularyAndRegister?: VocabularyAndRegister;
  paragraphStructure?: ParagraphStructureConfig;
  toneAndVoice?: ToneAndVoice;
  transitions?: Transitions;
  citations?: Citations;
  rhetoricalPatterns?: RhetoricalPatterns;
  representativeExcerpts?: string[];
  // Legacy flat format fields
  averageSentenceLength?: string;
  vocabularyComplexity?: string;
  passiveVoiceFrequency?: string;
  paragraphStructure_legacy?: string;
  citationDensity?: string;
  toneDescriptors?: string[];
  preferredTransitions?: string[];
  sampleExcerpts?: string[];
}

interface SentenceLevel {
  averageLength?: string;
  structureVariety?: string;
  commonOpeners?: string[];
  passiveVoice?: string;
}

interface VocabularyAndRegister {
  complexity?: string;
  registerLevel?: string;
  firstPersonUsage?: string;
  hebrewConventions?: string;
}

interface ParagraphStructureConfig {
  pattern?: string;
  argumentProgression?: string;
  evidenceIntroduction?: string;
  evidenceAnalysis?: string;
}

interface ToneAndVoice {
  descriptors?: string[];
  authorStance?: string;
  hedgingPatterns?: string[];
}

interface Transitions {
  preferred?: Record<string, string[]>;
}

interface Citations {
  integrationStyle?: string;
  density?: string;
  footnotesPerParagraph?: string;
  quoteLengthPreference?: string;
}

interface RhetoricalPatterns {
  common?: string[];
  emphasisTechniques?: string[];
}

interface ArticleStructure {
  sections?: string[];
  introPattern?: string;
  conclusionPattern?: string;
}

interface OutputFormatPreferences {
  font?: string;
  bodySize?: number;
  titleSize?: number;
  lineSpacing?: number;
  margins?: string;
  rtl?: boolean;
}
