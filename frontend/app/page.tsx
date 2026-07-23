"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type CSSProperties,
} from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { DEFAULT_API_BASE, liuyaoApi } from "./api";
import type {
  DivinationResponse,
  HexagramInfo,
  LineInfo,
  QiguaMethod,
} from "./types";

const METHOD_OPTIONS: Array<{
  id: QiguaMethod;
  name: string;
  note: string;
  mark: string;
}> = [
  { id: "time", name: "时间起卦", note: "依问卦时刻", mark: "时" },
  { id: "coin", name: "铜钱起卦", note: "模拟三钱六掷", mark: "钱" },
  { id: "manual", name: "手动起卦", note: "录入六爻结果", mark: "爻" },
  { id: "random", name: "随机起卦", note: "即刻生成卦象", mark: "随" },
];

const YAO_OPTIONS = [
  { value: 1, label: "少阴", symbol: "⚋", note: "静" },
  { value: 2, label: "少阳", symbol: "⚊", note: "静" },
  { value: 3, label: "老阳", symbol: "⚊", note: "动" },
  { value: 4, label: "老阴", symbol: "⚋", note: "动" },
];

const POSITION_NAMES: Record<number, string> = {
  1: "初爻",
  2: "二爻",
  3: "三爻",
  4: "四爻",
  5: "五爻",
  6: "上爻",
};

const COIN_RESULTS: Record<
  number,
  { code: number; label: string; symbol: string; moving: boolean }
> = {
  0: { code: 4, label: "老阴", symbol: "⚋", moving: true },
  1: { code: 2, label: "少阳", symbol: "⚊", moving: false },
  2: { code: 1, label: "少阴", symbol: "⚋", moving: false },
  3: { code: 3, label: "老阳", symbol: "⚊", moving: true },
};

interface CoinRound {
  faces: number[];
  code: number;
  label: string;
  symbol: string;
  moving: boolean;
}

type ResultTab = "paipan" | "texts" | "interpretation";
type AppView = "workspace" | "history";

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

function localDateTimeValue() {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  return now.toISOString().slice(0, 16);
}

function scoreTone(score: number) {
  if (score >= 2) return "strong";
  if (score <= -2) return "weak";
  return "neutral";
}

function YaoSymbol({
  line,
  compact = false,
}: {
  line: LineInfo;
  compact?: boolean;
}) {
  const isYang = line.line_type.includes("阳");
  return (
    <span
      className={`yao-symbol ${isYang ? "yang" : "yin"} ${
        compact ? "compact" : ""
      }`}
      aria-label={`${line.line_type}${line.is_changing ? "，动爻" : ""}`}
    >
      {isYang ? (
        <i />
      ) : (
        <>
          <i />
          <i />
        </>
      )}
      {line.is_changing && (
        <b className={isYang ? "moving-dot" : "moving-ring"} />
      )}
    </span>
  );
}

function MiniHexagram({ hexagram }: { hexagram: HexagramInfo }) {
  return (
    <div className="mini-hexagram" aria-hidden="true">
      {[...hexagram.lines]
        .sort((a, b) => b.position - a.position)
        .map((line) => (
          <YaoSymbol key={line.position} line={line} compact />
        ))}
    </div>
  );
}

function HexagramBoard({
  title,
  hexagram,
}: {
  title: string;
  hexagram: HexagramInfo;
}) {
  const sortedLines = useMemo(
    () => [...hexagram.lines].sort((a, b) => b.position - a.position),
    [hexagram.lines],
  );

  return (
    <section className="hexagram-card">
      <header className="hexagram-heading">
        <div>
          <span className="eyebrow">{title}</span>
          <h3>{hexagram.name}</h3>
          <p>
            {hexagram.palace} · {hexagram.gua_type}
          </p>
        </div>
        <MiniHexagram hexagram={hexagram} />
      </header>

      <div className="line-column-head" aria-hidden="true">
        <span>六神 · 六亲</span>
        <span>卦象</span>
        <span>纳甲五行</span>
        <span>旺衰</span>
      </div>

      <div className="hexagram-lines">
        {sortedLines.map((line) => (
          <div
            className={`hexagram-line ${line.is_changing ? "changing" : ""}`}
            key={line.position}
          >
            <div className="line-relations">
              <span>{line.liushen}</span>
              <strong>{line.liuqin || "—"}</strong>
            </div>
            <div className="line-mark">
              <YaoSymbol line={line} />
              <small>{POSITION_NAMES[line.position]}</small>
            </div>
            <div className="line-najia">
              <strong>
                {line.tiangan}
                {line.dizhi}
              </strong>
              <span>{line.wuxing}</span>
              {line.shiying !== "---" && (
                <em className={line.shiying === "世" ? "shi" : "ying"}>
                  {line.shiying}
                </em>
              )}
            </div>
            <div className="line-strength">
              <strong className={scoreTone(line.score)}>
                {line.score > 0 ? "+" : ""}
                {line.score.toFixed(1)}
              </strong>
              <span>{line.status.length ? line.status.join(" · ") : "平"}</span>
            </div>
          </div>
        ))}
      </div>

      <footer className="hexagram-footer">
        <span>
          世爻 <strong>{hexagram.shi_yao_position}</strong> ·{" "}
          {hexagram.shi_yao_dizhi}
        </span>
        <span>
          应爻 <strong>{hexagram.ying_yao_position}</strong> ·{" "}
          {hexagram.ying_yao_dizhi}
        </span>
      </footer>
    </section>
  );
}

function TextsPanel({ result }: { result: DivinationResponse }) {
  const sections = [
    { label: "本卦", hexagram: result.paipan.ben_gua },
    ...(result.paipan.bian_gua
      ? [{ label: "变卦", hexagram: result.paipan.bian_gua }]
      : []),
  ];

  return (
    <div className="texts-grid">
      {sections.map(({ label, hexagram }) => (
        <article className="classic-text-card" key={label}>
          <div className="classic-title">
            <span>{label}</span>
            <h3>{hexagram.name}</h3>
          </div>
          <blockquote>{hexagram.guaci || "暂无卦辞"}</blockquote>
          <ol reversed>
            {[...hexagram.yaoci].reverse().map((text, index) => (
              <li key={`${label}-${index}`}>{text}</li>
            ))}
          </ol>
        </article>
      ))}
    </div>
  );
}

function SimpleMarkdown({ content }: { content: string }) {
  const trimmed = content.trim();
  const outerFence = trimmed.match(
    /^```(?:markdown|md)?[ \t]*\n([\s\S]*?)\n```[ \t]*$/i,
  );
  const markdown = outerFence ? outerFence[1] : trimmed;

  return (
    <div className="markdown-body">
      <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml>
        {markdown}
      </ReactMarkdown>
    </div>
  );
}

function EmptyResult() {
  return (
    <section className="empty-result">
      <div className="cosmos-mark" aria-hidden="true">
        <span className="cosmos-ring" />
        <span className="cosmos-ring inner-ring" />
        <span className="cosmos-yin">☯</span>
      </div>
      <p className="eyebrow">问事 · 起卦 · 明理</p>
      <h2>一念既起，六爻成象</h2>
      <p className="empty-copy">
        在左侧写下此刻最想询问的一件事，选择起卦方式。
        <br />
        系统将为你排出本卦、变卦与六亲旺衰。
      </p>
      <div className="empty-steps">
        <span><b>壹</b> 诚心问事</span>
        <i />
        <span><b>贰</b> 选择起卦</span>
        <i />
        <span><b>叁</b> 观象明理</span>
      </div>
    </section>
  );
}

export default function Home() {
  const [view, setView] = useState<AppView>("workspace");
  const [question, setQuestion] = useState("");
  const [method, setMethod] = useState<QiguaMethod>("time");
  const [manualNumbers, setManualNumbers] = useState([2, 1, 2, 2, 1, 2]);
  const [dateTime, setDateTime] = useState(localDateTimeValue);
  const [coinRounds, setCoinRounds] = useState<CoinRound[]>([]);
  const [coinFaces, setCoinFaces] = useState<number[]>([1, 0, 1]);
  const [coinFlipping, setCoinFlipping] = useState(false);
  const [result, setResult] = useState<DivinationResponse | null>(null);
  const [resultTab, setResultTab] = useState<ResultTab>("paipan");
  const [history, setHistory] = useState<DivinationResponse[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [interpreting, setInterpreting] = useState(false);
  const [apiStatus, setApiStatus] = useState<"checking" | "online" | "offline">(
    "checking",
  );
  const [apiBase, setApiBase] = useState(DEFAULT_API_BASE);
  const [apiDraft, setApiDraft] = useState(DEFAULT_API_BASE);
  const [toast, setToast] = useState("");
  const [deleteCandidate, setDeleteCandidate] = useState<string | null>(null);

  const showToast = useCallback((message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(""), 3200);
  }, []);

  const checkApi = useCallback(
    async (base: string) => {
      setApiStatus("checking");
      try {
        await liuyaoApi.health(base);
        setApiStatus("online");
      } catch {
        setApiStatus("offline");
      }
    },
    [],
  );

  useEffect(() => {
    let cancelled = false;
    async function restoreApiSettings() {
      await Promise.resolve();
      if (cancelled) return;
      const saved = window.localStorage.getItem("liuyao-api-base");
      const base = saved || DEFAULT_API_BASE;
      setApiBase(base);
      setApiDraft(base);
      void checkApi(base);
    }
    void restoreApiSettings();
    return () => {
      cancelled = true;
    };
  }, [checkApi]);

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const ids = await liuyaoApi.list(apiBase);
      const records = await Promise.all(
        ids.slice(0, 30).map((id) => liuyaoApi.get(apiBase, id)),
      );
      setHistory(records);
    } catch (error) {
      showToast(error instanceof Error ? error.message : "历史记录加载失败");
    } finally {
      setHistoryLoading(false);
    }
  }, [apiBase, showToast]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!question.trim()) {
      showToast("请先写下所问事项");
      return;
    }
    if (method === "time" && !dateTime) {
      showToast("请选择起卦时间");
      return;
    }
    if (method === "coin" && coinRounds.length < 6) {
      showToast(`请先完成六次投掷（当前 ${coinRounds.length}/6）`);
      return;
    }
    setSubmitting(true);
    try {
      const response = await liuyaoApi.create(apiBase, {
        method: method === "coin" ? "manual" : method,
        question: question.trim(),
        ...(method === "manual" ? { numbers: manualNumbers } : {}),
        ...(method === "coin"
          ? { numbers: coinRounds.map((round) => round.code) }
          : {}),
        ...(method === "time" && dateTime
          ? { time: new Date(dateTime).toISOString() }
          : {}),
        generate_markdown: true,
      });
      setResult(response);
      setResultTab("paipan");
      setApiStatus("online");
      setView("workspace");
      showToast("排盘已完成");
    } catch (error) {
      setApiStatus("offline");
      showToast(error instanceof Error ? error.message : "起卦失败");
    } finally {
      setSubmitting(false);
    }
  }

  function handleCoinFlip() {
    if (coinFlipping || coinRounds.length >= 6) return;
    setCoinFlipping(true);

    window.setTimeout(() => {
      const randomValues = new Uint32Array(3);
      window.crypto.getRandomValues(randomValues);
      const faces = Array.from(randomValues, (value) => value % 2);
      const yangCount = faces.reduce((total, face) => total + face, 0);
      const result = COIN_RESULTS[yangCount];

      setCoinFaces(faces);
      setCoinRounds((rounds) => [
        ...rounds,
        {
          faces,
          code: result.code,
          label: result.label,
          symbol: result.symbol,
          moving: result.moving,
        },
      ]);
      setCoinFlipping(false);
    }, 720);
  }

  function resetCoinCasting() {
    setCoinRounds([]);
    setCoinFaces([1, 0, 1]);
    setCoinFlipping(false);
  }

  async function handleInterpret() {
    if (!result) return;
    setInterpreting(true);
    try {
      if (!result.markdown_content) {
        await liuyaoApi.generateMarkdown(apiBase, result.divination_id);
      }
      const response = await liuyaoApi.interpret(apiBase, result.divination_id);
      setResult(response);
      setResultTab("interpretation");
      showToast("AI 解读已生成");
    } catch (error) {
      showToast(error instanceof Error ? error.message : "AI 解读失败");
    } finally {
      setInterpreting(false);
    }
  }

  async function handleDelete(id: string) {
    if (deleteCandidate !== id) {
      setDeleteCandidate(id);
      window.setTimeout(() => setDeleteCandidate(null), 4000);
      return;
    }
    try {
      await liuyaoApi.remove(apiBase, id);
      setHistory((items) => items.filter((item) => item.divination_id !== id));
      if (result?.divination_id === id) setResult(null);
      setDeleteCandidate(null);
      showToast("记录已删除");
    } catch (error) {
      showToast(error instanceof Error ? error.message : "删除失败");
    }
  }

  function openHistoryItem(record: DivinationResponse) {
    setResult(record);
    setResultTab(record.interpretation?.detail ? "interpretation" : "paipan");
    setView("workspace");
  }

  function openHistory() {
    setView("history");
    void loadHistory();
  }

  function downloadMarkdown() {
    if (!result?.markdown_content) {
      showToast("当前记录没有 Markdown 内容");
      return;
    }
    const blob = new Blob([result.markdown_content], {
      type: "text/markdown;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `六爻排盘-${result.divination_id}.md`;
    link.click();
    URL.revokeObjectURL(url);
  }

  function saveApiBase(event: React.FormEvent) {
    event.preventDefault();
    const next = apiDraft.trim().replace(/\/+$/, "");
    if (!next) return;
    window.localStorage.setItem("liuyao-api-base", next);
    setApiBase(next);
    void checkApi(next);
    showToast("API 地址已保存");
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <button
          type="button"
          className="brand"
          onClick={() => setView("workspace")}
          aria-label="返回起卦工作台"
        >
          <span className="brand-seal">易</span>
          <span>
            <strong>大衍</strong>
            <small>六爻问事</small>
          </span>
        </button>

        <nav aria-label="主导航">
          <button
            type="button"
            className={view === "workspace" ? "active" : ""}
            onClick={() => setView("workspace")}
          >
            起卦工作台
          </button>
          <button
            type="button"
            className={view === "history" ? "active" : ""}
            onClick={openHistory}
          >
            历史卦例
          </button>
        </nav>

        <div className={`api-status ${apiStatus}`}>
          <i />
          {apiStatus === "online"
            ? "服务已连接"
            : apiStatus === "checking"
              ? "正在连接"
              : "服务未连接"}
        </div>
      </header>

      {view === "workspace" ? (
        <main className="workspace">
          <aside className="casting-panel">
            <form onSubmit={handleSubmit}>
              <div className="panel-title">
                <span>01</span>
                <div>
                  <h1>此刻，所问何事？</h1>
                  <p>一事一问，心诚则灵</p>
                </div>
              </div>

              <label className="question-field">
                <span>所问事项</span>
                <textarea
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  placeholder="例如：未来三个月的工作发展如何？"
                  maxLength={200}
                />
                <small>{question.length} / 200</small>
              </label>

              <fieldset>
                <legend>选择起卦方式</legend>
                <div className="method-grid">
                  {METHOD_OPTIONS.map((option) => (
                    <button
                      type="button"
                      key={option.id}
                      className={method === option.id ? "selected" : ""}
                      onClick={() => setMethod(option.id)}
                      aria-pressed={method === option.id}
                    >
                      <span>{option.mark}</span>
                      <strong>{option.name}</strong>
                      <small>{option.note}</small>
                    </button>
                  ))}
                </div>
              </fieldset>

              {method === "manual" && (
                <div className="manual-casting">
                  <div className="manual-note">
                    <span>从初爻至上爻依次录入</span>
                    <small>3、4 为动爻</small>
                  </div>
                  <div className="manual-lines">
                    {manualNumbers.map((number, index) => {
                      const option = YAO_OPTIONS[number - 1];
                      return (
                        <label key={index}>
                          <span>{POSITION_NAMES[index + 1]}</span>
                          <b>{option.symbol}</b>
                          <select
                            value={number}
                            onChange={(event) => {
                              const next = [...manualNumbers];
                              next[index] = Number(event.target.value);
                              setManualNumbers(next);
                            }}
                            aria-label={`${POSITION_NAMES[index + 1]}爻型`}
                          >
                            {YAO_OPTIONS.map((item) => (
                              <option value={item.value} key={item.value}>
                                {item.label} · {item.note}
                              </option>
                            ))}
                          </select>
                        </label>
                      );
                    })}
                  </div>
                </div>
              )}

              {method === "coin" && (
                <div className="coin-casting">
                  <div className="coin-casting-head">
                    <div>
                      <strong>三枚铜钱 · 六次成卦</strong>
                      <span>花为阳，字为阴；从初爻依次向上</span>
                    </div>
                    <small>{coinRounds.length} / 6</small>
                  </div>

                  <div
                    className={`coins-stage ${coinFlipping ? "flipping" : ""}`}
                    aria-live="polite"
                  >
                    {coinFaces.map((face, index) => (
                      <span
                        className={`coin ${face ? "flower" : "character"}`}
                        key={index}
                        style={{ "--coin-index": index } as CSSProperties}
                      >
                        <i>{face ? "花" : "字"}</i>
                      </span>
                    ))}
                  </div>

                  <button
                    type="button"
                    className="throw-coins"
                    onClick={handleCoinFlip}
                    disabled={coinFlipping || coinRounds.length >= 6}
                  >
                    {coinFlipping
                      ? "铜钱翻转中…"
                      : coinRounds.length >= 6
                        ? "六次投掷已完成"
                        : `投掷第 ${coinRounds.length + 1} 次`}
                  </button>

                  <div className="coin-rounds" aria-label="六次投掷结果">
                    {Array.from({ length: 6 }, (_, index) => {
                      const round = coinRounds[index];
                      return (
                        <div
                          className={`coin-round ${
                            round?.moving ? "moving" : ""
                          }`}
                          key={index}
                        >
                          <span>{POSITION_NAMES[index + 1]}</span>
                          {round ? (
                            <>
                              <b>{round.symbol}</b>
                              <strong>{round.label}</strong>
                              <small>
                                {round.faces
                                  .map((face) => (face ? "花" : "字"))
                                  .join(" · ")}
                              </small>
                            </>
                          ) : (
                            <em>待投掷</em>
                          )}
                        </div>
                      );
                    })}
                  </div>

                  {coinRounds.length > 0 && (
                    <button
                      type="button"
                      className="reset-coins"
                      onClick={resetCoinCasting}
                      disabled={coinFlipping}
                    >
                      重新投掷
                    </button>
                  )}
                </div>
              )}

              {method === "time" && (
                <label className="time-setting">
                  <span>
                    起卦时间
                    <small>请选择你要用于起卦的具体时间</small>
                  </span>
                  <input
                    type="datetime-local"
                    value={dateTime}
                    onChange={(event) => setDateTime(event.target.value)}
                    aria-label="起卦时间"
                    required
                  />
                </label>
              )}

              <button
                className="cast-button"
                type="submit"
                disabled={
                  submitting || (method === "coin" && coinRounds.length < 6)
                }
              >
                <span>
                  {submitting
                    ? "正在推演"
                    : method === "coin"
                      ? coinRounds.length < 6
                        ? `还需投掷 ${6 - coinRounds.length} 次`
                        : "以六爻结果起卦"
                      : "开始起卦"}
                </span>
                <i>{submitting ? "···" : "→"}</i>
              </button>
              <p className="form-hint">将生成完整排盘并保存至历史记录</p>
            </form>

            <details className="api-settings">
              <summary>接口设置</summary>
              <form onSubmit={saveApiBase}>
                <label htmlFor="api-base">FastAPI 服务地址</label>
                <div>
                  <input
                    id="api-base"
                    value={apiDraft}
                    onChange={(event) => setApiDraft(event.target.value)}
                    placeholder="http://127.0.0.1:8022"
                  />
                  <button type="submit">保存</button>
                </div>
              </form>
            </details>
          </aside>

          <section className="result-panel">
            {!result ? (
              <EmptyResult />
            ) : (
              <div className="result-content">
                <header className="result-header">
                  <div>
                    <span className="record-id">卦例 #{result.divination_id}</span>
                    <h2>{result.paipan.question}</h2>
                    <p>{formatDateTime(result.paipan.qigua_time)} 起卦</p>
                  </div>
                  <div className="result-actions">
                    <button type="button" onClick={downloadMarkdown}>
                      ↓ 导出排盘
                    </button>
                    <button
                      type="button"
                      className="primary"
                      onClick={handleInterpret}
                      disabled={interpreting}
                    >
                      {interpreting ? "正在参详…" : "AI 解读"}
                    </button>
                  </div>
                </header>

                <div className="calendar-strip">
                  {(["year", "month", "day", "hour"] as const).map(
                    (key, index) => (
                      <div key={key}>
                        <span>{["年柱", "月柱", "日柱", "时柱"][index]}</span>
                        <strong>{result.paipan.ganzhi[key]}</strong>
                      </div>
                    ),
                  )}
                  <div className="xunkong">
                    <span>旬空</span>
                    <strong>{result.paipan.xunkong.join("") || "—"}</strong>
                  </div>
                  <div className="moving-summary">
                    <span>动爻</span>
                    <strong>
                      {result.paipan.moving_positions.length
                        ? result.paipan.moving_positions
                            .map((position) => POSITION_NAMES[position])
                            .join("、")
                        : "无动爻"}
                    </strong>
                  </div>
                </div>

                <div className="result-tabs" role="tablist">
                  {[
                    ["paipan", "排盘详情"],
                    ["texts", "卦辞爻辞"],
                    ["interpretation", "AI 解读"],
                  ].map(([id, label]) => (
                    <button
                      type="button"
                      key={id}
                      className={resultTab === id ? "active" : ""}
                      onClick={() => setResultTab(id as ResultTab)}
                      role="tab"
                      aria-selected={resultTab === id}
                    >
                      {label}
                      {id === "interpretation" &&
                        result.interpretation?.detail && <i />}
                    </button>
                  ))}
                </div>

                {resultTab === "paipan" && (
                  <div className="hexagram-grid">
                    <HexagramBoard
                      title="本卦"
                      hexagram={result.paipan.ben_gua}
                    />
                    {result.paipan.bian_gua ? (
                      <HexagramBoard
                        title="变卦"
                        hexagram={result.paipan.bian_gua}
                      />
                    ) : (
                      <section className="no-change-card">
                        <span>静</span>
                        <h3>此卦无动爻</h3>
                        <p>本卦即为所测之卦，无变卦。</p>
                      </section>
                    )}
                  </div>
                )}

                {resultTab === "texts" && <TextsPanel result={result} />}

                {resultTab === "interpretation" && (
                  <section className="interpretation-panel">
                    {result.interpretation?.detail ? (
                      <>
                        <div className="interpretation-heading">
                          <span>AI 参详</span>
                          <p>基于当前排盘与传统六爻规则生成</p>
                        </div>
                        <SimpleMarkdown content={result.interpretation.detail} />
                      </>
                    ) : (
                      <div className="interpretation-empty">
                        <span>解</span>
                        <h3>尚未生成解读</h3>
                        <p>调用当前 LiuYao Analyst，对用神、动变与吉凶趋势作综合参详。</p>
                        <button
                          type="button"
                          onClick={handleInterpret}
                          disabled={interpreting}
                        >
                          {interpreting ? "正在参详…" : "生成 AI 解读"}
                        </button>
                      </div>
                    )}
                    <p className="disclaimer">
                      {result.interpretation?.disclaimer ||
                        "本结果仅供文化娱乐参考，不构成任何人生决策依据。"}
                    </p>
                  </section>
                )}
              </div>
            )}
          </section>
        </main>
      ) : (
        <main className="history-page">
          <header className="history-heading">
            <div>
              <span className="eyebrow">往事可鉴</span>
              <h1>历史卦例</h1>
              <p>回看每一次问事与所得之象</p>
            </div>
            <button type="button" onClick={() => void loadHistory()}>
              ↻ 刷新记录
            </button>
          </header>

          {historyLoading ? (
            <div className="history-loading">正在翻阅卦册…</div>
          ) : history.length ? (
            <div className="history-list">
              {history.map((record) => (
                <article className="history-card" key={record.divination_id}>
                  <button
                    type="button"
                    className="history-main"
                    onClick={() => openHistoryItem(record)}
                  >
                    <MiniHexagram hexagram={record.paipan.ben_gua} />
                    <div className="history-copy">
                      <span>
                        #{record.divination_id} ·{" "}
                        {formatDateTime(record.paipan.qigua_time)}
                      </span>
                      <h2 title={record.paipan.question}>
                        {record.paipan.question}
                      </h2>
                      <p>
                        {record.paipan.ben_gua.name}
                        {record.paipan.bian_gua
                          ? ` → ${record.paipan.bian_gua.name}`
                          : " · 静卦"}
                      </p>
                    </div>
                    <strong>查看排盘 →</strong>
                  </button>
                  <button
                    type="button"
                    className={`delete-record ${
                      deleteCandidate === record.divination_id ? "confirm" : ""
                    }`}
                    onClick={() => void handleDelete(record.divination_id)}
                    aria-label={`删除卦例 ${record.divination_id}`}
                  >
                    {deleteCandidate === record.divination_id ? "确认删除" : "删除"}
                  </button>
                </article>
              ))}
            </div>
          ) : (
            <div className="history-empty">
              <span>册</span>
              <h2>暂无卦例</h2>
              <p>完成第一次起卦后，记录会出现在这里。</p>
              <button type="button" onClick={() => setView("workspace")}>
                前往起卦
              </button>
            </div>
          )}
        </main>
      )}

      <footer className="site-footer">
        <span>大衍六爻 · 传统文化数字化探索</span>
        <span>本结果仅供文化娱乐参考，不构成任何人生决策依据</span>
      </footer>

      {toast && <div className="toast" role="status">{toast}</div>}
    </div>
  );
}
