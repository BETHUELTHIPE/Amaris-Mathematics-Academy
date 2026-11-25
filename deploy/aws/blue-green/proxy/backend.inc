proxy_pass http://127.0.0.1:8000;
proxy_http_version 1.1;
proxy_set_header Host 16.171.164.5;
proxy_set_header X-Forwarded-Host 16.171.164.5;
proxy_set_header X-Forwarded-Proto https;
proxy_set_header X-Forwarded-For $http_x_amaris_client_ip;
