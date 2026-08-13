export type QiguaMethod = "manual" | "coin" | "time" | "random";

export interface QiguaRequest {
  method: QiguaMethod;
  question: string;
  time?: string;
  numbers?: number[];
  generate_markdown: boolean;
}

export interface LineInfo {
  position: number;
  liushen: string;
  liuqin: string;
  line_type: string;
  symbol: string;
  moving_mark: string;
  tiangan: string;
  dizhi: string;
  wuxing: string;
  shiying: string;
  is_changing: boolean;
  score: number;
  status: string[];
}

export interface HexagramInfo {
  palace: string;
  gua_type: string;
  name: string;
  guaci: string;
  yaoci: string[];
  shi_yao_position: number;
  ying_yao_position: number;
  shi_yao_dizhi: string;
  ying_yao_dizhi: string;
  lines: LineInfo[];
}

export interface PaipanResult {
  divination_id: string;
  question: string;
  qigua_time: string;
  ganzhi: Record<"year" | "month" | "day" | "hour", string>;
  xunkong: string[];
  ben_gua: HexagramInfo;
  bian_gua: HexagramInfo | null;
  moving_positions: number[];
}

export interface InterpretationResult {
  summary: string | null;
  detail: string | null;
  yongshen_analysis: string | null;
  dongbian_analysis: string | null;
  disclaimer: string;
}

export interface DivinationResponse {
  divination_id: string;
  paipan: PaipanResult;
  interpretation: InterpretationResult | null;
  markdown_path: string | null;
  markdown_content: string | null;
}

export interface MarkdownResponse {
  divination_id: string;
  path: string | null;
  content: string;
}

export interface UserResponse {
  id: string;
  user_type: "guest" | "registered";
  username: string | null;
  display_name: string | null;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AuthResponse {
  user: UserResponse;
}

export interface UserLLMSettings {
  base_url: string;
  api_key_configured: boolean;
  api_key_last4: string;
  model: string;
  analyst_model: string | null;
  suggestion_model: string | null;
  memory_model: string | null;
  timeout_seconds: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface UserLLMSettingsInput {
  base_url: string;
  api_key?: string;
  model: string;
  analyst_model?: string | null;
  suggestion_model?: string | null;
  memory_model?: string | null;
  timeout_seconds?: number;
}

export type ChatSessionStatus = "active" | "archived";
export type ChatMessageRole = "user" | "assistant" | "system" | "tool";
export type ChatMessageType =
  | "text"
  | "tool_call"
  | "tool_result"
  | "summary"
  | "suggestions";
export type ChatMessageStatus =
  | "pending"
  | "completed"
  | "failed"
  | "cancelled";

export interface ChatSession {
  id: string;
  user_id: string;
  title: string | null;
  status: ChatSessionStatus;
  active_divination_id: string | null;
  summary: string | null;
  summary_through_sequence: number;
  summary_through_agent_message_id: number;
  summary_updated_at: string | null;
  model: string | null;
  created_at: string;
  updated_at: string;
  last_message_at: string;
}

export interface ChatSessionOpenResult {
  created: boolean;
  related_session_count: number;
  session: ChatSession;
}

export interface ChatMessage {
  id: string;
  session_id: string;
  source_message_id: string | null;
  divination_id: string | null;
  sequence: number;
  role: ChatMessageRole;
  message_type: ChatMessageType;
  content: string | null;
  tool_name: string | null;
  tool_call_id: string | null;
  payload: unknown;
  status: ChatMessageStatus;
  token_count: number | null;
  created_at: string;
  updated_at: string;
}

export interface ChatToolResult {
  success: boolean;
  model_content: string;
  display_content: string | null;
  data: unknown;
  error_code: string | null;
  retryable: boolean;
}

export type ChatEventType =
  | "run_started"
  | "text_delta"
  | "tool_call_started"
  | "tool_call_completed"
  | "tool_call_failed"
  | "message_completed"
  | "suggestions"
  | "error";

export interface ChatEvent {
  event_type: ChatEventType;
  request_id: string | null;
  content: string | null;
  tool_call_id: string | null;
  tool_name: string | null;
  tool_arguments: unknown;
  tool_result: ChatToolResult | null;
  error_code: string | null;
  retryable: boolean;
  message_id: string | null;
  source_message_id: string | null;
  questions: string[] | null;
}

export interface ChatSuggestionsResponse {
  source_message_id: string;
  questions: string[];
  cached: boolean;
}

export interface ChatRunCancelResponse {
  request_id: string;
  status: "cancelled" | "cancelling" | "already_finished";
  message: string;
}
