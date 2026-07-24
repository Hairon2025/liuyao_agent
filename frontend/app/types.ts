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
  display_name: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}
