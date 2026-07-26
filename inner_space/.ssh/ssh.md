# SSH管理

通过 SSH 连接远程主机。配置存储在 `ssh.json`，使用 `ssh_manager.py` 管理。

## 使用方式

工作目录为 `inner_space/.ssh/`：

**添加SSH：**
```
python3 ssh_manager.py add '{"name":"<名称>","host":"<IP>","port":22,"username":"<用户>","auth_type":"password|key","password":"<密码>","key_path":"<密钥路径>","desc":"<说明>"}'
```

**删除SSH：**
```
python3 ssh_manager.py del <SSH名称>
```

**列出SSH：**
```
python3 ssh_manager.py list
```

## 注意事项

- 需要连接远程主机时，直接读取 `ssh.json` 获取连接信息，不要询问用户
- 新增连接按字段模板创建：`name`（名称）、`host`（主机）、`port`（端口）、`username`（用户名）、`auth_type`（认证类型：password/key）、`password`（密码）、`key_path`（密钥路径）

## 当前SSH

| 名称 | 主机 | 端口 | 用户 | 认证方式 |
|------|------|------|------|----------|
| `aliyun-ecs` | 8.130.188.188 | 22 | root | key |
