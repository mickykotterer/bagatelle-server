timeout = 120
max_requests = 200        # recycle worker after N requests, releasing accumulated RSS
max_requests_jitter = 50  # stagger recycling so it's not deterministic
workers = 1