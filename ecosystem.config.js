module.exports = {
  apps: [
    {
      name: 'bigdata-flask',
      script: 'C:/Users/LENOVO/AppData/Local/Python/pythoncore-3.14-64/python.exe',
      args: 'dashboard/app.py',
      cwd: 'd:/AI/01_Products/BigData',
      interpreter: 'none',
      autorestart: true,
      max_restarts: 10,
      env: {
        PYTHONPATH: 'd:/AI/01_Products/BigData',
        PYTHONUTF8: '1',
        PYTHONIOENCODING: 'utf-8'
      }
    },
    {
      name: 'bigdata-streamlit',
      script: 'C:/Users/LENOVO/AppData/Local/Python/pythoncore-3.14-64/python.exe',
      args: '-m streamlit run src/dashboard/app.py --server.port 8502 --server.headless true',
      cwd: 'd:/AI/01_Products/BigData',
      interpreter: 'none',
      autorestart: true,
      max_restarts: 10,
      env: {
        PYTHONPATH: 'd:/AI/01_Products/BigData',
        PYTHONUTF8: '1',
        PYTHONIOENCODING: 'utf-8'
      }
    }
  ]
};
