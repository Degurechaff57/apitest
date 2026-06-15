# 小红书个人主页 API 文档

Base URL: `ENV:BASE_URL`

## 认证说明

所有需要登录的接口需携带 Header:
```
Authorization: Bearer <token>
```

Token 通过登录接口获取。

---

## 1. 用户认证

### POST /api/auth/login

用户登录获取 token。

**Request Body:**
| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| phone | string | 是 | 手机号（11位） |
| code | string | 是 | 短信验证码（6位） |

**Response (200):**
```json
{
  "code": 200,
  "message": "登录成功",
  "data": { "token": "eyJ...", "userId": 1001, "nickname": "小美" }
}
```

**Error (401):**
```json
{ "code": 401, "message": "验证码错误" }
```

---

## 2. 用户信息

### GET /api/user/profile

获取当前登录用户或指定用户的个人信息。

**Query Parameters:**
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| userId | int | 否 | 目标用户ID，不填则返回当前用户 |

**Response (200):**
```json
{
  "code": 200,
  "data": {
    "userId": 1001,
    "nickname": "小美",
    "avatar": "https://cdn.example.com/avatars/1001.jpg",
    "bio": "热爱生活的旅行博主 ✈️",
    "gender": 1,
    "followerCount": 12500,
    "followingCount": 389,
    "noteCount": 156,
    "verified": { "type": "personal", "desc": "时尚领域优质创作者" },
    "tags": ["摄影", "旅行", "探店", "美食"],
    "joinDate": "2023-03-15"
  }
}
```

**Error (404):**
```json
{ "code": 404, "message": "用户不存在" }
```

### PUT /api/user/profile

编辑个人资料。需要登录。

**Request Body:**
| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| nickname | string | 否 | 1-20字符，支持中英文数字 |
| bio | string | 否 | 最多100字 |
| gender | int | 否 | 0=保密, 1=男, 2=女 |

**Response (200):**
```json
{
  "code": 200,
  "message": "更新成功",
  "data": { "nickname": "小美_new", "bio": "新的简介" }
}
```

**Error (409):**
```json
{ "code": 409, "message": "该昵称已被使用，请尝试添加后缀（如小美_123）" }
```

### POST /api/user/avatar

上传头像。需要登录。

**Request Body (multipart/form-data):**
| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| file | file | 是 | JPG/PNG，≤2MB |

**Response (200):**
```json
{
  "code": 200,
  "message": "上传成功",
  "data": { "avatarUrl": "https://cdn.example.com/avatars/1001_new.jpg" }
}
```

**Error (400):**
```json
{ "code": 400, "message": "文件过大，最大支持2MB" }
```

---

## 3. 关注系统

### POST /api/user/follow

关注用户。需要登录。

**Request Body:**
| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| targetUserId | int | 是 | 要关注的用户ID |

**Response (200):**
```json
{
  "code": 200,
  "message": "关注成功",
  "data": { "isMutual": false }
}
```

**Error (400):**
```json
{ "code": 400, "message": "今日关注已达上限（500人）" }
```

### DELETE /api/user/follow

取关用户。需要登录。

**Request Body:**
| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| targetUserId | int | 是 | 要取关的用户ID |

**Response (200):**
```json
{ "code": 200, "message": "已取消关注" }
```

### GET /api/user/followers

获取粉丝列表（分页）。需要登录。

**Query Parameters:**
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| userId | int | 否 | 用户ID，不填默认当前用户 |
| page | int | 否 | 页码，默认1 |
| pageSize | int | 否 | 每页条数，默认20 |

**Response (200):**
```json
{
  "code": 200,
  "data": {
    "total": 12500,
    "page": 1,
    "pageSize": 20,
    "list": [
      { "userId": 1002, "nickname": "旅行达人", "avatar": "..." },
      { "userId": 1003, "nickname": "美食家小王", "avatar": "..." }
    ]
  }
}
```

---

## 4. 内容模块

### GET /api/user/notes

获取用户笔记列表（分页）。需要登录。

**Query Parameters:**
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| userId | int | 否 | 用户ID |
| tab | string | 否 | 分类：notes(笔记), collected(收藏), liked(赞过)，默认notes |
| page | int | 否 | 页码，默认1 |
| pageSize | int | 否 | 每页条数，默认10 |

**Response (200):**
```json
{
  "code": 200,
  "data": {
    "total": 156,
    "page": 1,
    "pageSize": 10,
    "hasMore": true,
    "list": [
      {
        "noteId": 2001,
        "title": "周末露营装备推荐",
        "cover": "https://cdn.example.com/covers/2001.jpg",
        "likeCount": 2340,
        "commentCount": 89,
        "hasProduct": true,
        "productPrice": 99.00,
        "createTime": "2025-06-10 14:30:00"
      }
    ]
  }
}
```

### GET /api/notes/{noteId}

获取笔记详情。需要登录。

**Response (200):**
```json
{
  "code": 200,
  "data": {
    "noteId": 2001,
    "title": "周末露营装备推荐",
    "content": "最近入手的露营装备分享...",
    "images": ["url1", "url2", "url3"],
    "tags": ["露营", "装备"],
    "author": { "userId": 1001, "nickname": "小美", "avatar": "..." },
    "likeCount": 2340,
    "collectCount": 567,
    "commentCount": 89,
    "isLiked": false,
    "isCollected": false,
    "createTime": "2025-06-10 14:30:00"
  }
}
```

**Error (404):**
```json
{ "code": 404, "message": "笔记不存在" }
```

### POST /api/notes/{noteId}/like

点赞笔记。需要登录。

**Response (200):**
```json
{
  "code": 200,
  "message": "点赞成功",
  "data": { "likeCount": 2341, "isLiked": true }
}
```

### DELETE /api/notes/{noteId}/like

取消点赞。

**Response (200):**
```json
{ "code": 200, "message": "已取消点赞" }
```

### POST /api/notes/{noteId}/collect

收藏笔记。需要登录。

**Response (200):**
```json
{
  "code": 200,
  "message": "收藏成功",
  "data": { "collectCount": 568, "isCollected": true }
}
```

### GET /api/notes/{noteId}/comments

获取评论列表（分页）。

**Query Parameters:**
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| page | int | 否 | 页码，默认1 |
| pageSize | int | 否 | 每页条数，默认20 |

**Response (200):**
```json
{
  "code": 200,
  "data": {
    "total": 89,
    "page": 1,
    "pageSize": 20,
    "list": [
      {
        "commentId": 3001,
        "userId": 1002,
        "nickname": "旅行达人",
        "content": "这个帐篷好用吗？",
        "likeCount": 12,
        "createTime": "2025-06-11 09:15:00"
      }
    ]
  }
}
```

### POST /api/notes/{noteId}/comments

发表评论。需要登录。

**Request Body:**
| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| content | string | 是 | 评论内容（1-500字） |
| replyTo | int | 否 | 回复的评论ID |

**Response (200):**
```json
{
  "code": 200,
  "message": "评论成功",
  "data": { "commentId": 3090, "content": "质量很好！" }
}
```

**Error (400):**
```json
{ "code": 400, "message": "评论包含违规内容" }
```

---

## 5. 搜索

### GET /api/search

搜索用户或笔记。

**Query Parameters:**
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| keyword | string | 是 | 搜索关键词 |
| type | string | 否 | user 或 note，默认note |
| page | int | 否 | 页码，默认1 |
| pageSize | int | 否 | 每页条数，默认20 |

**Response (200):**
```json
{
  "code": 200,
  "data": {
    "keyword": "露营",
    "total": 1200,
    "list": [
      {
        "noteId": 2001,
        "title": "<em>露营</em>装备推荐",
        "author": { "nickname": "小美" },
        "likeCount": 2340
      }
    ]
  }
}
```

---

## 6. 隐私设置

### GET /api/user/privacy

获取隐私设置。需要登录。

**Response (200):**
```json
{
  "code": 200,
  "data": {
    "contentVisibility": "public",
    "allowStrangerMessage": false,
    "showFollowerList": true
  }
}
```

### PUT /api/user/privacy

更新隐私设置。需要登录。

**Request Body:**
| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| contentVisibility | string | 否 | public, followers, private |
| allowStrangerMessage | bool | 否 | 是否允许陌生人私信 |
| showFollowerList | bool | 否 | 是否公开粉丝列表 |

**Response (200):**
```json
{
  "code": 200,
  "message": "隐私设置已更新"
}
```
