---
date: 2025-12-28T15:06:22+00:00
researcher: AI Assistant
topic: "Username/Password Authentication Implementation for React + FastAPI"
tags: [research, authentication, react, fastapi, jwt, security, react-auth-kit, fastapi-users]
status: complete
last_updated: 2025-12-28
last_updated_by: AI Assistant
---

# Research: Username/Password Authentication Implementation for React + FastAPI

**Date**: 2025-12-28T15:06:22+00:00  
**Researcher**: AI Assistant

## Research Question

What is the most loved React authentication package as of December 2025 that works with FastAPI for implementing username/password authentication with JWT tokens on both frontend and backend?

## Summary

Based on comprehensive research of current trends (December 2025), codebase analysis, and documentation review, the recommended authentication stack is:

**Frontend**: **React Auth Kit** (`react-auth-kit`) - A lightweight, JWT-focused library with 137 code snippets, high source reputation, and native support for both cookie and bearer token authentication.

**Backend**: **FastAPI Users** (`fastapi-users`) - The most comprehensive and battle-tested authentication solution for FastAPI with 277 code snippets, ready-to-use JWT authentication, user registration, and password management.

**Alternative consideration**: While **NextAuth.js** is the most popular overall React auth library in 2025, it's primarily designed for Next.js applications. For a standalone React + Vite application (like this codebase), React Auth Kit is more appropriate.

### Why This Stack?

1. **React Auth Kit** provides exactly what's needed:
   - Native JWT support (both bearer tokens and HTTP-only cookies)
   - Lightweight and framework-agnostic (works with React + Vite)
   - Simple API with hooks and HOCs
   - Automatic token refresh support
   - No vendor lock-in

2. **FastAPI Users** is production-ready:
   - Complete user management (registration, login, password reset)
   - Multiple authentication backends (JWT, Cookie, OAuth2)
   - SQLAlchemy integration for user storage
   - Secure password hashing with Argon2
   - Extensible and customizable

3. **Perfect compatibility**: Both libraries use standard JWT tokens and OAuth2 password flow, ensuring seamless integration.

## Detailed Findings

### Web Research: Current Authentication Landscape (December 2025)

#### Most Popular React Auth Libraries

**1. NextAuth.js** ([/nextauthjs/next-auth](https://github.com/nextauthjs/next-auth))
- **Benchmark Score**: 91.8 (highest)
- **Code Snippets**: 1,083
- **Source Reputation**: High
- **Best for**: Next.js applications
- **Limitation**: Primarily designed for Next.js, not ideal for standalone React + Vite apps

**2. React Auth Kit** ([/react-auth-kit/react-auth-kit](https://github.com/react-auth-kit/react-auth-kit))
- **Code Snippets**: 137
- **Source Reputation**: High
- **Best for**: Lightweight JWT authentication in any React app
- **Key Features**:
  - Token-based authentication (JWT)
  - Cookie and Bearer token support
  - Refresh token handling
  - React Router integration
  - Framework-agnostic

**3. Auth0 React** ([/auth0/auth0-react](https://github.com/auth0/auth0-react))
- **Benchmark Score**: 86.6
- **Code Snippets**: 329
- **Source Reputation**: High
- **Best for**: Applications using Auth0 as identity provider
- **Limitation**: Requires Auth0 service (not self-hosted)

**4. Better Auth** ([/websites/better-auth](https://www.better-auth.com))
- **Benchmark Score**: 75.5
- **Code Snippets**: 1,774
- **Source Reputation**: High
- **Best for**: Framework-agnostic TypeScript authentication
- **Note**: Newer library, still gaining adoption

#### FastAPI Authentication Libraries

**1. FastAPI Users** ([/fastapi-users/fastapi-users](https://github.com/fastapi-users/fastapi-users))
- **Benchmark Score**: 73.0
- **Code Snippets**: 277
- **Source Reputation**: High
- **Features**:
  - Ready-to-use user registration and authentication
  - Multiple authentication backends (JWT, Cookie, OAuth2)
  - SQLAlchemy integration
  - Password hashing with Argon2
  - Customizable user models
  - Email verification and password reset

**2. FastAPI JWT** ([/k4black/fastapi-jwt](https://github.com/k4black/fastapi-jwt))
- **Code Snippets**: 26
- **Source Reputation**: High
- **Features**:
  - Native JWT extension for FastAPI
  - Access/refresh token support
  - OpenAPI schema generation
  - Cookie support

**3. Native FastAPI OAuth2** (Built-in)
- **Source**: FastAPI documentation
- **Features**:
  - OAuth2PasswordBearer scheme
  - OAuth2PasswordRequestForm
  - JWT token generation with PyJWT
  - Password hashing with pwdlib

### Codebase Analysis

#### Current Architecture

**Backend** (`backend/`):
- **Framework**: FastAPI with Uvicorn
- **API Structure**: Router-based (`routes.py`) under `/api` prefix
- **Models**: Pydantic for API schemas, dataclasses for internal state
- **State Management**: In-memory dictionary + file-based persistence
- **CORS**: Configured in `main.py` with `ALLOWED_ORIGINS` environment variable
- **Current Auth**: **None** - No authentication or user management implemented

**Frontend** (`frontend/src/`):
- **Framework**: React + TypeScript + Vite
- **API Client**: Auto-generated OpenAPI TypeScript client (`@hey-api/openapi-ts`)
- **State Management**: React hooks (`useState`, `useEffect`) + Context for theme
- **API Wrapper**: Custom `api-client.ts` with error handling
- **Current Auth**: Generated auth utilities exist (`client/core/auth.gen.ts`) but **not used**

#### Key Integration Points

**Backend Files to Modify**:
- `backend/main.py` - Add FastAPI Users initialization
- `backend/routes.py` - Add auth router and protect existing routes
- `backend/models.py` - Add User model
- `backend/requirements.txt` - Add `fastapi-users[sqlalchemy]`, `pwdlib[argon2]`

**Frontend Files to Modify**:
- `frontend/package.json` - Add `react-auth-kit`
- `frontend/src/main.tsx` - Wrap app with `AuthProvider`
- `frontend/src/api-client.ts` - Add auth token to API requests
- `frontend/src/components/` - Add Login/Register components
- `frontend/src/App.tsx` - Add protected route logic

**New Files Needed**:
- `backend/database.py` - SQLAlchemy setup for user storage
- `backend/auth.py` - FastAPI Users configuration
- `frontend/src/components/Login.tsx` - Login form
- `frontend/src/components/Register.tsx` - Registration form
- `frontend/src/contexts/AuthContext.tsx` - Optional: centralized auth state

### Implementation Pattern: JWT Bearer Token Flow

#### Backend Flow (FastAPI Users)

1. **User Registration** (`POST /auth/register`):
   ```python
   # Request
   {
     "email": "user@example.com",
     "password": "securepassword"
   }
   
   # Response
   {
     "id": "uuid",
     "email": "user@example.com",
     "is_active": true,
     "is_verified": false
   }
   ```

2. **User Login** (`POST /auth/jwt/login`):
   ```python
   # Request (form data)
   username=user@example.com
   password=securepassword
   
   # Response
   {
     "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
     "token_type": "bearer"
   }
   ```

3. **Protected Routes**:
   ```python
   from fastapi_users import FastAPIUsers
   
   @router.get("/notebooks")
   async def list_notebooks(user: User = Depends(current_active_user)):
       # Only authenticated users can access
       return notebooks
   ```

#### Frontend Flow (React Auth Kit)

1. **App Setup**:
   ```typescript
   import { AuthProvider, createStore } from 'react-auth-kit'
   
   const store = createStore({
     authName: '_auth',
     authType: 'cookie',
     cookieDomain: window.location.hostname,
     cookieSecure: window.location.protocol === 'https:',
   })
   
   <AuthProvider store={store}>
     <App />
   </AuthProvider>
   ```

2. **Login Component**:
   ```typescript
   import { useSignIn } from 'react-auth-kit'
   
   const signIn = useSignIn()
   
   const handleLogin = async (email, password) => {
     const response = await api.login(email, password)
     
     signIn({
       auth: {
         token: response.access_token,
         type: 'Bearer'
       },
       userState: { email }
     })
   }
   ```

3. **Protected API Calls**:
   ```typescript
   import { useAuthHeader } from 'react-auth-kit'
   
   const authHeader = useAuthHeader()
   
   // Add to API client
   client.setConfig({
     headers: {
       Authorization: authHeader()
     }
   })
   ```

### Code References from Documentation

#### FastAPI Users - JWT Authentication Setup

From [fastapi-users documentation](https://github.com/fastapi-users/fastapi-users):

```python
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)

SECRET = "SECRET"  # Should be from environment variable

bearer_transport = BearerTransport(tokenUrl="auth/jwt/login")

def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=SECRET, lifetime_seconds=3600)

auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)
```

#### React Auth Kit - Integration Example

From [react-auth-kit documentation](https://github.com/react-auth-kit/react-auth-kit):

```typescript
import { AuthProvider, createStore } from 'react-auth-kit'

const store = createStore({
  authName: '_auth',
  authType: 'cookie',
  cookieDomain: window.location.hostname,
  cookieSecure: window.location.protocol === 'https:',
})

function App() {
  return (
    <AuthProvider store={store}>
      <Routes />
    </AuthProvider>
  )
}
```

### Security Best Practices

#### Password Security
- **Hashing**: Use Argon2 (via `pwdlib[argon2]`)
- **Never store plain text passwords**
- **Salt automatically handled by pwdlib**

#### JWT Token Security
- **Short expiration**: 1 hour for access tokens
- **Refresh tokens**: Implement for long-lived sessions
- **HTTPS only**: Set `cookieSecure: true` in production
- **HttpOnly cookies**: Prevents XSS attacks

#### CORS Configuration
- **Update backend CORS**: Add production frontend domain
- **Credentials**: Set `allow_credentials=True` for cookies
- **Specific origins**: Never use `*` in production

```python
# backend/main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://your-cloudfront-domain.cloudfront.net"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Architecture Insights

### Current System Patterns

1. **Stateless API Design**: Current notebook API is RESTful and stateless (except for in-memory storage)
2. **OpenAPI Integration**: Frontend uses generated TypeScript client from OpenAPI spec
3. **WebSocket for Real-time**: Separate WebSocket connection for cell execution updates
4. **No Session Management**: Currently no concept of users or sessions

### Authentication Integration Strategy

**Phase 1: Add User Management** (Backend)
- Install FastAPI Users and SQLAlchemy
- Create User model and database tables
- Add authentication routes (`/auth/register`, `/auth/jwt/login`)
- Keep existing notebook routes unchanged initially

**Phase 2: Associate Notebooks with Users** (Backend)
- Add `user_id` field to Notebook model
- Protect notebook routes with authentication
- Filter notebooks by current user

**Phase 3: Frontend Authentication** (Frontend)
- Install React Auth Kit
- Create Login/Register components
- Wrap app with AuthProvider
- Add token to API client requests
- Add protected route logic

**Phase 4: Deployment Updates**
- Update CORS for production domain
- Set JWT secret from environment variable
- Configure database connection for user storage
- Update health check to verify auth system

### Data Flow with Authentication

```
User → Login Form → POST /auth/jwt/login → FastAPI Users
                                          ↓
                                    Verify Password (Argon2)
                                          ↓
                                    Generate JWT Token
                                          ↓
                                    Return Token to Frontend
                                          ↓
React Auth Kit stores token → All API calls include Authorization header
                                          ↓
Backend validates JWT → Extracts user_id → Returns user-specific data
```

## Historical Context (from thoughts/)

### Deployment Documentation

From `thoughts/shared/plans/2025-12-28-aws-terraform-deployment-implementation.md`:

**Current CORS Configuration**:
- Hardcoded for local development (`localhost:3000`, `localhost:5173`)
- Located in `backend/main.py:12`
- Needs environment variable configuration for production

**Production Deployment Architecture**:
- Frontend: S3 + CloudFront
- Backend: ECS Fargate behind ALB
- WebSocket support via ALB sticky sessions
- Single-task deployment due to in-memory state

**Authentication Considerations** (from deployment plan):
> "Future enhancements could include:
> - User authentication (Cognito, Auth0, or custom JWT)
> - API key authentication for programmatic access"

This research provides the foundation for implementing custom JWT authentication as mentioned in the deployment roadmap.

### API Design Patterns

From `thoughts/shared/plans/2025-12-27-openapi-ts-integration.md`:

**Current API Client Pattern**:
- Auto-generated from OpenAPI spec
- Custom wrapper in `api-client.ts` for error handling
- Centralized configuration in `client.setConfig()`

**Authentication Integration Point**:
The existing API client architecture already supports authentication via the generated `auth.gen.ts` utilities. We just need to:
1. Configure the auth header in the client
2. Provide the JWT token from React Auth Kit

## Related Research

- `thoughts/shared/research/2025-12-28-aws-terraform-deployment-strategy.md` - Infrastructure and CORS configuration
- `thoughts/shared/research/2025-12-27-openapi-ts-integration.md` - API client architecture
- `thoughts/shared/plans/2025-12-28-aws-terraform-deployment-implementation.md` - Production deployment requirements

## Implementation Checklist

### Backend (FastAPI)

- [ ] Install dependencies:
  ```bash
  pip install fastapi-users[sqlalchemy] pwdlib[argon2] pyjwt
  ```

- [ ] Create `backend/database.py`:
  - SQLAlchemy engine and session
  - User table definition
  - Database initialization

- [ ] Create `backend/auth.py`:
  - User model (FastAPI Users)
  - JWT authentication backend
  - FastAPIUsers instance
  - Current user dependencies

- [ ] Update `backend/main.py`:
  - Import and include auth router
  - Update CORS to allow credentials
  - Add JWT secret from environment

- [ ] Update `backend/models.py`:
  - Add `user_id` field to Notebook model
  - Add user relationship

- [ ] Update `backend/routes.py`:
  - Add `current_active_user` dependency to protected routes
  - Filter notebooks by user_id
  - Associate new notebooks with current user

### Frontend (React)

- [ ] Install dependencies:
  ```bash
  npm install react-auth-kit
  ```

- [ ] Update `frontend/src/main.tsx`:
  - Import and configure AuthProvider
  - Wrap App with AuthProvider

- [ ] Create `frontend/src/components/Login.tsx`:
  - Login form with email/password
  - Call `/auth/jwt/login` endpoint
  - Store token with useSignIn hook

- [ ] Create `frontend/src/components/Register.tsx`:
  - Registration form
  - Call `/auth/register` endpoint
  - Redirect to login on success

- [ ] Update `frontend/src/api-client.ts`:
  - Add auth header to all requests
  - Use useAuthHeader hook
  - Handle 401 errors (redirect to login)

- [ ] Update `frontend/src/App.tsx`:
  - Add login/register routes
  - Protect notebook routes with RequireAuth
  - Add logout functionality

### Database

- [ ] Choose database:
  - **Development**: SQLite (file-based)
  - **Production**: PostgreSQL (RDS or existing postgres container)

- [ ] Create migration script:
  - Initialize user tables
  - Add user_id to existing notebooks

### Testing

- [ ] Test user registration flow
- [ ] Test login and token generation
- [ ] Test protected routes (with and without token)
- [ ] Test notebook isolation (users only see their notebooks)
- [ ] Test logout and token expiration
- [ ] Test CORS with production domain

### Deployment

- [ ] Update environment variables:
  - `JWT_SECRET` - Random secret for JWT signing
  - `DATABASE_URL` - Connection string for user database
  - `ALLOWED_ORIGINS` - Include production frontend URL

- [ ] Update Terraform:
  - Add RDS instance for user database (or use existing postgres)
  - Add environment variables to ECS task definition
  - Update security groups for database access

## Open Questions

1. **Database Strategy**: Should we use the existing PostgreSQL container (from `postgres/docker-compose.yml`) for user storage, or create a separate RDS instance?
   - **Recommendation**: Use existing PostgreSQL for development, add RDS for production

2. **Notebook Ownership**: Should we migrate existing notebooks to a default user, or start fresh?
   - **Recommendation**: Add a migration script to assign existing notebooks to a default "admin" user

3. **Registration Flow**: Should registration be open, or require invitation/admin approval?
   - **Recommendation**: Start with open registration, add approval flow later if needed

4. **Session Duration**: What should the JWT token lifetime be?
   - **Recommendation**: 1 hour access token, 7 days refresh token

5. **WebSocket Authentication**: How should we authenticate WebSocket connections?
   - **Recommendation**: Pass JWT token as query parameter: `/api/ws/notebooks/{id}?token={jwt}`

## External Resources

### Documentation Links

- **React Auth Kit**: https://authkit.arkadip.dev/
- **FastAPI Users**: https://fastapi-users.github.io/fastapi-users/
- **FastAPI Security Tutorial**: https://fastapi.tiangolo.com/tutorial/security/
- **JWT.io**: https://jwt.io/ (for debugging JWT tokens)

### Example Implementations

- **FastAPI + React Auth Example**: https://github.com/Buuntu/fastapi-react
- **FastAPI OIDC React**: https://github.com/kolitiri/fastapi-oidc-react
- **JWT Authentication Tutorial**: https://www.youtube.com/watch?v=YpvcqxYiyNE

### Security Resources

- **OWASP Authentication Cheat Sheet**: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- **JWT Best Practices**: https://tools.ietf.org/html/rfc8725

## Conclusion

The combination of **React Auth Kit** (frontend) and **FastAPI Users** (backend) provides a production-ready, secure, and maintainable authentication solution for the Reactive Notebook application. Both libraries are actively maintained, well-documented, and follow security best practices.

The implementation can be done incrementally:
1. Add backend authentication infrastructure
2. Integrate frontend authentication UI
3. Protect existing routes and associate data with users
4. Deploy with proper environment configuration

This approach minimizes disruption to the existing codebase while adding essential user management capabilities for production deployment.

