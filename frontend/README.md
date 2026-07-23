# 大衍 · 六爻问事前端

基于项目 FastAPI 接口实现的六爻起卦与排盘工作台。

## 功能

- 时间、铜钱、手动、随机四种起卦方式
- 本卦 / 变卦、六神、六亲、纳甲、旺衰与世应展示
- 卦辞爻辞阅读
- Agent 解读调用与 Markdown 导出
- 历史卦例查看、刷新与删除
- 可配置 FastAPI 服务地址

## 本地启动

```bash
npm install
npm run dev
```

默认连接 `http://127.0.0.1:8022`。如需修改，复制 `.env.example`
为 `.env.local`，或在页面底部的“接口设置”中保存新地址。

## 验证

```bash
npm run lint
npm run build
```
