// Cloudflare Worker: принимает команды из Telegram и запускает отчёт в GitHub Actions.
//
// Переменные (Settings → Variables and Secrets):
//   TG_BOT_TOKEN       — токен бота (секрет)
//   TG_WEBHOOK_SECRET  — любая длинная случайная строка (секрет), та же, что при setWebhook
//   TG_CHAT_ID         — chat_id рабочего чата (пока пусто — работает только /chatid)
//   GH_TOKEN           — fine-grained токен GitHub с правом Actions: Read and write на репозиторий (секрет)
//   GH_REPO            — владелец/репозиторий, например my-login/instagram-report
//
// Команды:  /report — отчёт сейчас;  /chatid — показать id чата (для настройки).

export default {
  async fetch(request, env) {
    if (request.method !== "POST") return new Response("ok");
    if (request.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.TG_WEBHOOK_SECRET) {
      return new Response("forbidden", { status: 403 });
    }
    const update = await request.json();
    const msg = update.message || update.channel_post;
    if (!msg || !msg.text) return new Response("ok");

    const cmd = msg.text.trim().split(/[\s@]/)[0].toLowerCase();
    const chatId = String(msg.chat.id);

    if (cmd === "/chatid") {
      await reply(env, chatId, `chat_id этого чата: ${chatId}`);
    } else if (cmd === "/report") {
      if (!env.TG_CHAT_ID || chatId !== String(env.TG_CHAT_ID)) return new Response("ok");
      const r = await fetch(
        `https://api.github.com/repos/${env.GH_REPO}/actions/workflows/report.yml/dispatches`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${env.GH_TOKEN}`,
            Accept: "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "instagram-report-bot",
          },
          body: JSON.stringify({ ref: "main", inputs: { mode: "manual" } }),
        },
      );
      await reply(env, chatId, r.ok
        ? "⏳ Готовлю отчёт, пришлю через 1–2 минуты."
        : `❗ Не удалось запустить отчёт (GitHub ответил ${r.status}).`);
    }
    return new Response("ok");
  },
};

async function reply(env, chatId, text) {
  await fetch(`https://api.telegram.org/bot${env.TG_BOT_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, text }),
  });
}
