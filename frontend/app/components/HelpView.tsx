"use client";

const DEEPSEEK_LINKS = {
  platform: "https://platform.deepseek.com/",
  keys: "https://platform.deepseek.com/api_keys",
  topUp: "https://platform.deepseek.com/top_up",
  docs: "https://api-docs.deepseek.com/",
  pricing: "https://api-docs.deepseek.com/quick_start/pricing/",
};

function ExternalLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noreferrer">
      {children}
      <span aria-hidden="true">↗</span>
    </a>
  );
}

export function HelpView({
  onStart,
  onOpenSettings,
}: {
  onStart: () => void;
  onOpenSettings: () => void;
}) {
  return (
    <main className="help-page">
      <header className="help-hero">
        <div>
          <span className="eyebrow">使用指南</span>
          <h1>从一念所问，到一卦明理</h1>
          <p>
            第一次使用可以从这里开始。起卦与排盘无需模型；AI 解读和问易聊天
            需要登录，并配置自己的模型 API Key。
          </p>
          <div className="help-hero-actions">
            <button type="button" onClick={onStart}>开始起卦</button>
            <button type="button" onClick={onOpenSettings}>账户与模型设置</button>
          </div>
        </div>
        <aside aria-label="快速流程">
          <span>一</span><i />
          <span>卦</span><i />
          <span>问</span>
          <small>诚心问事 · 选择起卦 · 观象明理</small>
        </aside>
      </header>

      <nav className="help-toc" aria-label="帮助目录">
        <a href="#help-start">快速开始</a>
        <a href="#help-casting">四种起卦</a>
        <a href="#help-ai">AI 功能</a>
        <a href="#help-deepseek">配置 DeepSeek</a>
        <a href="#help-troubleshooting">常见问题</a>
      </nav>

      <div className="help-layout">
        <article className="help-content">
          <section id="help-start" className="help-section">
            <div className="help-section-heading">
              <span>01</span>
              <div>
                <p>QUICK START</p>
                <h2>四步完成第一次起卦</h2>
              </div>
            </div>
            <ol className="help-steps">
              <li>
                <b>1</b>
                <div><strong>写下所问之事</strong><p>尽量一事一问，并写清关心的时间范围与背景。</p></div>
              </li>
              <li>
                <b>2</b>
                <div><strong>选择起卦方式</strong><p>时间、铜钱、手动或随机均可，按真实情况选择。</p></div>
              </li>
              <li>
                <b>3</b>
                <div><strong>查看排盘</strong><p>系统会生成本卦、变卦、六亲、六神、旺衰与卦爻辞。</p></div>
              </li>
              <li>
                <b>4</b>
                <div><strong>解读或继续问易</strong><p>登录并配置模型后，可生成完整报告或围绕卦例多轮追问。</p></div>
              </li>
            </ol>
            <div className="help-tip">
              <strong>提问示例</strong>
              <p>“未来三个月是否适合更换工作？”比“我的未来怎么样？”更容易得到聚焦的分析。</p>
            </div>
          </section>

          <section id="help-casting" className="help-section">
            <div className="help-section-heading">
              <span>02</span>
              <div><p>CASTING</p><h2>选择适合你的起卦方式</h2></div>
            </div>
            <div className="help-methods">
              <div><i>时</i><strong>时间起卦</strong><p>输入实际起卦时间，由年月日时生成卦象。</p></div>
              <div><i>钱</i><strong>铜钱起卦</strong><p>前端模拟三枚铜钱，依次投掷六次，从初爻向上成卦。</p></div>
              <div><i>爻</i><strong>手动起卦</strong><p>适合已经得到六次结果的情况；页面上爻在上、初爻在下。</p></div>
              <div><i>随</i><strong>随机起卦</strong><p>没有现成时间或铜钱结果时，可让系统即时生成一卦。</p></div>
            </div>
            <div className="help-coin-table" role="table" aria-label="铜钱结果与爻型对应表">
              <div role="row"><strong role="columnheader">铜钱结果</strong><strong role="columnheader">爻型</strong><strong role="columnheader">状态</strong></div>
              <div role="row"><span role="cell">3 花</span><span role="cell">老阳 ⚊</span><span role="cell">动爻</span></div>
              <div role="row"><span role="cell">2 花 1 字</span><span role="cell">少阴 ⚋</span><span role="cell">静爻</span></div>
              <div role="row"><span role="cell">1 花 2 字</span><span role="cell">少阳 ⚊</span><span role="cell">静爻</span></div>
              <div role="row"><span role="cell">3 字</span><span role="cell">老阴 ⚋</span><span role="cell">动爻</span></div>
            </div>
          </section>

          <section id="help-ai" className="help-section">
            <div className="help-section-heading">
              <span>03</span>
              <div><p>AI FEATURES</p><h2>AI 解读与问易有什么区别</h2></div>
            </div>
            <div className="help-ai-grid">
              <div>
                <span>解</span>
                <strong>生成 AI 解读</strong>
                <p>针对当前排盘生成一次完整报告，结果会保存到这条卦例中，适合先获得整体判断。</p>
              </div>
              <div>
                <span>问</span>
                <strong>问易聊天</strong>
                <p>可以让助手起卦、读取已有卦例，也可以围绕用神、动爻、应期等内容继续追问。</p>
              </div>
            </div>
            <ul className="help-notes">
              <li>游客可以起卦和排盘；AI 解读与问易需要登录账号。</li>
              <li>每名用户使用自己配置的 API Key，模型费用由对应平台账户承担。</li>
              <li>回答后的追问建议会额外调用一次模型，可在模型设置中关闭或指定轻量模型。</li>
              <li>历史卦例中的“问易”会优先恢复这条卦例已有的会话，也可以另开新讨论。</li>
            </ul>
          </section>

          <section id="help-deepseek" className="help-section">
            <div className="help-section-heading">
              <span>04</span>
              <div><p>DEEPSEEK API</p><h2>获取并配置 DeepSeek API Key</h2></div>
            </div>
            <div className="help-deepseek-intro">
              <p>DeepSeek 网页聊天账号与开放平台 API 是两套使用场景。本项目需要的是开放平台 API Key，并按实际 Token 用量扣费。</p>
              <ExternalLink href={DEEPSEEK_LINKS.platform}>打开 DeepSeek 开放平台</ExternalLink>
            </div>
            <ol className="help-platform-steps">
              <li><b>01</b><div><strong>登录开放平台</strong><p>进入 DeepSeek 开放平台，使用你的账号完成登录。</p></div></li>
              <li><b>02</b><div><strong>检查账户余额</strong><p>API 调用会产生费用。测试前请确认账户有可用余额，价格以官方页面为准。</p><ExternalLink href={DEEPSEEK_LINKS.topUp}>前往充值</ExternalLink></div></li>
              <li><b>03</b><div><strong>创建 API Key</strong><p>进入 API Keys 页面创建新密钥，复制以 <code>sk-</code> 开头的内容，并妥善保存。</p><ExternalLink href={DEEPSEEK_LINKS.keys}>管理 API Keys</ExternalLink></div></li>
              <li><b>04</b><div><strong>填写到本项目</strong><p>登录本项目，点击右上角账户按钮，在“个人 LLM 配置”中填写下面的参数。</p></div></li>
            </ol>

            <div className="help-config-card">
              <div><span>Base URL</span><code>https://api.deepseek.com</code></div>
              <div><span>API Key</span><code>sk-你的密钥</code></div>
              <div><span>默认模型（经济快速）</span><code>deepseek-v4-flash</code></div>
              <div><span>默认模型（复杂分析）</span><code>deepseek-v4-pro</code></div>
            </div>

            <div className="help-config-finish">
              <strong>最后两步</strong>
              <p>点击“保存设置”，页面会自动关闭并提示成功。再次打开账户设置，可以点击“测试已保存配置”检查连接。</p>
              <button type="button" onClick={onOpenSettings}>现在去配置</button>
            </div>

            <div className="help-security-note">
              <strong>密钥安全</strong>
              <p>不要把 API Key 发给他人、贴到聊天内容或提交到公开仓库。本项目只向前端返回密钥尾号，完整密钥会在服务端加密保存。</p>
            </div>
          </section>

          <section id="help-troubleshooting" className="help-section">
            <div className="help-section-heading">
              <span>05</span>
              <div><p>TROUBLESHOOTING</p><h2>常见问题</h2></div>
            </div>
            <details><summary>为什么能排盘，却不能生成 AI 解读？</summary><p>排盘是本地算法，不需要模型。AI 功能要求注册登录，并保存有效的 Base URL、API Key 和模型名称。</p></details>
            <details><summary>模型连接测试失败怎么办？</summary><p>依次检查 API Key 是否完整、Base URL 是否为 <code>https://api.deepseek.com</code>、模型名称是否正确，以及开放平台是否有可用余额。</p></details>
            <details><summary>为什么问易会消耗较多 Token？</summary><p>多轮聊天会携带最近上下文，首次完整解读、记忆摘要和追问建议也可能产生独立调用。可以关闭追问建议，并避免在同一会话中混合无关问题。</p></details>
            <details><summary>删除或更换 API Key 后怎么办？</summary><p>在 DeepSeek 平台创建新密钥，然后回到个人 LLM 配置填写并保存。旧密钥留空只表示不修改，不会自动替换。</p></details>
          </section>
        </article>

        <aside className="help-side-card">
          <span>官方资源</span>
          <ExternalLink href={DEEPSEEK_LINKS.keys}>API Key 管理</ExternalLink>
          <ExternalLink href={DEEPSEEK_LINKS.pricing}>模型与计费</ExternalLink>
          <ExternalLink href={DEEPSEEK_LINKS.docs}>DeepSeek API 文档</ExternalLink>
          <p>平台模型与价格可能调整，请以官方页面的最新信息为准。</p>
        </aside>
      </div>
    </main>
  );
}
