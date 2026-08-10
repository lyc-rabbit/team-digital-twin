#!/bin/bash
# 团队数字孪生系统 —— 一键启动脚本

echo "========================================="
echo "  团队数字孪生系统 · 启动中"
echo "========================================="

# 加载环境变量
if [ -f backend/.env ]; then
  export $(cat backend/.env | grep -v '^#' | xargs)
  echo "[✓] 已加载 .env 配置"
else
  echo "[!] 未找到 backend/.env，将以降级模式运行"
  echo "    配置方法: cp backend/.env.example backend/.env && 填入 SILICONFLOW_API_KEY"
fi

# 启动后端
echo ""
echo "[1/2] 启动后端 (FastAPI :8000)..."
cd backend
python main.py &
BACKEND_PID=$!
cd ..

# 等待后端就绪
sleep 3

# 启动前端
echo "[2/2] 启动前端 (Vite :5173)..."
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "========================================="
echo "  系统已启动！"
echo "  前端: http://localhost:5173"
echo "  后端: http://localhost:8000/api"
echo "  API 文档: http://localhost:8000/docs"
echo "========================================="
echo ""
echo "按 Ctrl+C 停止所有服务"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" SIGINT SIGTERM
wait
