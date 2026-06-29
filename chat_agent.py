import asyncio
import threading
import customtkinter as ctk
from datetime import datetime
from weather_agent import ask_agent, load_preferences, save_preference

# 设置外观
ctk.set_appearance_mode("system")
ctk.set_default_color_theme("blue")

class ChatAgentApp:
    def __init__(self):
        self.window = ctk.CTk()
        self.window.title("🧠 生活助理")
        self.window.geometry("600x520")
        self.window.minsize(400, 400)

        # 标题
        title_label = ctk.CTkLabel(
            self.window,
            text="🧠 生活助理 · 随时待命",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_label.pack(pady=(10, 5))

        # 聊天显示区域（滚动框架）
        self.chat_frame = ctk.CTkScrollableFrame(
            self.window,
            width=560,
            orientation="vertical"
        )
        self.chat_frame.pack(pady=10, padx=15, fill="both", expand=True)

        # 底部输入区域
        input_frame = ctk.CTkFrame(self.window)
        input_frame.pack(pady=10, padx=15, fill="x")

        self.input_entry = ctk.CTkEntry(
            input_frame,
            placeholder_text="输入指令... (如: 明天上海天气怎么样?)",
            height=40
        )
        self.input_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.send_btn = ctk.CTkButton(
            input_frame,
            text="发送",
            width=80,
            height=40,
            command=self.send_message
        )
        self.send_btn.pack(side="right")

        # 绑定回车键
        self.window.bind('<Return>', lambda e: self.send_message())

        # 启动时显示欢迎语
        self.add_message("system", "🌅 早上好！我是你的生活助理。随时可以问我天气、日程或任何生活问题。")

    def add_message(self, sender: str, text: str):
        """向聊天界面添加消息（超紧凑版）"""
        timestamp = datetime.now().strftime("%H:%M")

        if sender == "user":
            prefix = "🧑 我"
            color = ("#1a1a2e", "#ffffff")
            bg = ("#e0e7ff", "#2d2d44")
        elif sender == "system":
            prefix = "🤖 助理"
            color = ("#1a1a2e", "#a0aec0")
            bg = "transparent"
        else:  # agent
            prefix = "🤖 助理"
            color = ("#1a1a2e", "#e2e8f0")
            bg = ("#f0f4f8", "#2d2d44")

        msg_frame = ctk.CTkFrame(
            self.chat_frame,
            corner_radius=6,
            fg_color=bg,
            width=500
        )
        msg_frame.pack(pady=2, padx=10, anchor="w", fill="x")
        msg_frame.pack_propagate(False)

        label = ctk.CTkLabel(
            msg_frame,
            text=f"[{timestamp}] {prefix}\n{text}",
            font=ctk.CTkFont(size=12),
            text_color=color,
            justify="left",
            wraplength=500
        )
        label.pack(pady=4, padx=10, anchor="w")

        # 强制滚动到底部
        self.chat_frame._parent_canvas.yview_moveto(1.0)
        self.chat_frame.update_idletasks()

    def send_message(self):
        user_input = self.input_entry.get().strip()
        if not user_input:
            return

        self.input_entry.delete(0, "end")
        self.add_message("user", user_input)

        self.send_btn.configure(state="disabled")
        threading.Thread(target=self.run_agent_task, args=(user_input,), daemon=True).start()

    def run_agent_task(self, user_input: str):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self._run_agent_with_capture(user_input))
            loop.close()

            self.window.after(0, lambda: self.add_message("agent", result))
            self.window.after(0, lambda: self.send_btn.configure(state="normal"))
        except Exception as e:
            self.window.after(0, lambda: self.add_message("system", f"⚠️ 出错：{e}"))
            self.window.after(0, lambda: self.send_btn.configure(state="normal"))

    async def _run_agent_with_capture(self, user_input: str) -> str:
        return await ask_agent(user_input, max_steps=5)

    def run(self):
        self.window.mainloop()

if __name__ == "__main__":
    app = ChatAgentApp()
    app.run()
