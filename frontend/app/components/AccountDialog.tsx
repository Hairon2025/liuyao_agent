"use client";

import { useState } from "react";
import { liuyaoApi } from "../api";
import type {
  UserLLMSettings,
  UserLLMSettingsInput,
  UserResponse,
} from "../types";

export type AccountDialogMode = "login" | "register" | "settings";

interface AccountDialogProps {
  apiBase: string;
  open: boolean;
  mode: AccountDialogMode;
  user: UserResponse | null;
  settings: UserLLMSettings | null;
  onClose: () => void;
  onModeChange: (mode: AccountDialogMode) => void;
  onIdentityChange: (user: UserResponse) => void;
  onSettingsChange: (settings: UserLLMSettings | null) => void;
  onNotify: (message: string) => void;
}

const DEFAULT_FORM: UserLLMSettingsInput = {
  base_url: "https://api.deepseek.com",
  api_key: "",
  model: "deepseek-v4-pro",
  analyst_model: "",
  suggestion_model: "",
  memory_model: "",
  timeout_seconds: 120,
};

function settingsToForm(
  settings: UserLLMSettings | null,
): UserLLMSettingsInput {
  if (!settings) return DEFAULT_FORM;
  return {
    base_url: settings.base_url,
    api_key: "",
    model: settings.model,
    analyst_model: settings.analyst_model ?? "",
    suggestion_model: settings.suggestion_model ?? "",
    memory_model: settings.memory_model ?? "",
    timeout_seconds: settings.timeout_seconds,
  };
}

export function AccountDialog({
  apiBase,
  open,
  mode,
  user,
  settings,
  onClose,
  onModeChange,
  onIdentityChange,
  onSettingsChange,
  onNotify,
}: AccountDialogProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [form, setForm] = useState<UserLLMSettingsInput>(() =>
    settingsToForm(settings),
  );
  const [submitting, setSubmitting] = useState(false);
  const [testing, setTesting] = useState(false);

  if (!open) return null;

  const registered = user?.user_type === "registered";

  async function handleAuth(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    try {
      const response =
        mode === "register"
          ? await liuyaoApi.register(apiBase, {
              username,
              password,
              ...(displayName.trim()
                ? { display_name: displayName.trim() }
                : {}),
            })
          : await liuyaoApi.login(apiBase, { username, password });
      onIdentityChange(response.user);
      setPassword("");
      const saved = await liuyaoApi.getLLMSettings(apiBase);
      onSettingsChange(saved);
      if (saved) {
        onNotify(mode === "register" ? "账号注册成功" : "登录成功");
        onClose();
      } else {
        onNotify("账号已登录，请继续配置模型服务");
        onModeChange("settings");
      }
    } catch (error) {
      onNotify(error instanceof Error ? error.message : "身份验证失败");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSaveSettings(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    try {
      const payload: UserLLMSettingsInput = {
        ...form,
        api_key: form.api_key?.trim() || undefined,
        analyst_model: form.analyst_model?.trim() || null,
        suggestion_model: form.suggestion_model?.trim() || null,
        memory_model: form.memory_model?.trim() || null,
      };
      const saved = await liuyaoApi.saveLLMSettings(apiBase, payload);
      onSettingsChange(saved);
      setForm(settingsToForm(saved));
      onNotify("LLM 设置已保存");
    } catch (error) {
      onNotify(error instanceof Error ? error.message : "LLM 设置保存失败");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleTest() {
    setTesting(true);
    try {
      const result = await liuyaoApi.testLLMSettings(apiBase);
      onNotify(result.message);
    } catch (error) {
      onNotify(error instanceof Error ? error.message : "连接测试失败");
    } finally {
      setTesting(false);
    }
  }

  async function handleLogout() {
    setSubmitting(true);
    try {
      await liuyaoApi.logout(apiBase);
      const guest = await liuyaoApi.createGuest(apiBase);
      onIdentityChange(guest.user);
      onSettingsChange(null);
      onModeChange("login");
      onNotify("已退出登录，当前为游客模式");
      onClose();
    } catch (error) {
      onNotify(error instanceof Error ? error.message : "退出登录失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="account-dialog-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        className={`account-dialog ${
          mode === "settings" ? "settings-dialog" : "auth-dialog"
        }`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="account-dialog-title"
      >
        <button
          type="button"
          className="account-dialog-close"
          onClick={onClose}
          aria-label="关闭账户窗口"
        >
          ×
        </button>

        {mode !== "settings" ? (
          <>
            <header className="account-dialog-heading">
              <span>账户</span>
              <h2 id="account-dialog-title">
                {mode === "login" ? "登录问易" : "创建账号"}
              </h2>
              <p>AI 解读与问易需要登录，并使用你自己的模型配置。</p>
            </header>

            <div className="account-tabs" role="tablist">
              <button
                type="button"
                className={mode === "login" ? "active" : ""}
                onClick={() => onModeChange("login")}
              >
                登录
              </button>
              <button
                type="button"
                className={mode === "register" ? "active" : ""}
                onClick={() => onModeChange("register")}
              >
                注册
              </button>
            </div>

            <form
              className="account-form account-auth-form"
              onSubmit={handleAuth}
            >
              <label>
                <span>用户名</span>
                <input
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  minLength={3}
                  maxLength={32}
                  pattern="[A-Za-z0-9_]+"
                  autoComplete="username"
                  placeholder="字母、数字或下划线"
                  required
                />
              </label>
              {mode === "register" && (
                <label>
                  <span>称呼（可选）</span>
                  <input
                    value={displayName}
                    onChange={(event) => setDisplayName(event.target.value)}
                    maxLength={50}
                    autoComplete="name"
                    placeholder="页面中显示的称呼"
                  />
                </label>
              )}
              <label>
                <span>密码</span>
                <input
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  minLength={8}
                  maxLength={128}
                  autoComplete={
                    mode === "register" ? "new-password" : "current-password"
                  }
                  placeholder="至少 8 位"
                  required
                />
              </label>
              <button type="submit" className="account-primary" disabled={submitting}>
                {submitting
                  ? "正在处理…"
                  : mode === "login"
                    ? "登录"
                    : "注册并保留当前卦例"}
              </button>
            </form>
          </>
        ) : (
          <>
            <header className="account-dialog-heading">
              <span>模型设置</span>
              <h2 id="account-dialog-title">个人 LLM 配置</h2>
              <p>
                API Key 会加密保存，页面只显示尾号；未单独填写的子模型会使用默认模型。
              </p>
            </header>

            {!registered ? (
              <div className="account-empty">
                <p>请先登录账号，再配置模型服务。</p>
                <button type="button" onClick={() => onModeChange("login")}>
                  前往登录
                </button>
              </div>
            ) : (
              <form className="account-form llm-settings-form" onSubmit={handleSaveSettings}>
                <label className="full-row">
                  <span>Base URL</span>
                  <input
                    type="url"
                    value={form.base_url}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        base_url: event.target.value,
                      }))
                    }
                    placeholder="https://api.openai.com/v1"
                    required
                  />
                </label>
                <label className="full-row">
                  <span>API Key</span>
                  <input
                    type="password"
                    value={form.api_key ?? ""}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        api_key: event.target.value,
                      }))
                    }
                    autoComplete="off"
                    placeholder={
                      settings
                        ? `已保存 ····${settings.api_key_last4}（留空不修改）`
                        : "首次设置时必须填写"
                    }
                    required={!settings}
                  />
                </label>
                <label>
                  <span>默认模型</span>
                  <input
                    value={form.model}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        model: event.target.value,
                      }))
                    }
                    placeholder="gpt-4.1-mini"
                    required
                  />
                </label>
                {/* 暂不开放正式解读模型的独立配置，后端字段继续保留。 */}
                {/*
                  <label>
                    <span>正式解读模型（可选）</span>
                    <input
                      value={form.analyst_model ?? ""}
                      onChange={(event) =>
                        setForm((current) => ({
                          ...current,
                          analyst_model: event.target.value,
                        }))
                      }
                      placeholder="留空使用默认模型"
                    />
                  </label>
                */}
                <label>
                  <span>追问建议模型（可选）</span>
                  <input
                    value={form.suggestion_model ?? ""}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        suggestion_model: event.target.value,
                      }))
                    }
                    placeholder="可填写较轻量模型"
                  />
                </label>
                {/* 暂不开放记忆摘要模型的独立配置，后端字段继续保留。 */}
                {/*
                  <label>
                    <span>记忆摘要模型（可选）</span>
                    <input
                      value={form.memory_model ?? ""}
                      onChange={(event) =>
                        setForm((current) => ({
                          ...current,
                          memory_model: event.target.value,
                        }))
                      }
                      placeholder="可填写较轻量模型"
                    />
                  </label>
                */}
                <label>
                  <span>超时时间（秒）</span>
                  <input
                    type="number"
                    min={10}
                    max={300}
                    value={form.timeout_seconds ?? 120}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        timeout_seconds: Number(event.target.value),
                      }))
                    }
                  />
                </label>
                <div className="account-form-actions full-row">
                  <button type="submit" className="account-primary" disabled={submitting}>
                    {submitting ? "正在保存…" : "保存设置"}
                  </button>
                  <button
                    type="button"
                    className="account-secondary"
                    disabled={!settings || testing}
                    onClick={() => void handleTest()}
                  >
                    {testing ? "正在测试…" : "测试已保存配置"}
                  </button>
                </div>
              </form>
            )}

            {registered && (
              <footer className="account-dialog-footer">
                <span>
                  当前账号：{user.display_name || user.username}
                </span>
                <button type="button" disabled={submitting} onClick={() => void handleLogout()}>
                  退出登录
                </button>
              </footer>
            )}
          </>
        )}
      </section>
    </div>
  );
}
