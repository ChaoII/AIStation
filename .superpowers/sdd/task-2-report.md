# Task 2 — REST API + Service Layer

## Files created

| File | Purpose |
|------|---------|
| `backend/app/plugin/module_train/controller.py` | 9 endpoints on `APIRouter(prefix="/train")` — model CRUD, task CRUD + stop, eval CRUD |
| `backend/app/plugin/module_train/service.py` | `TrainService` class with all business logic using `async_db_session` |
| `backend/app/plugin/module_train/scheduler.py` | Placeholder `stop_training()` for Task 4 |

## Endpoints

| Method | Path | Permission | Handler |
|--------|------|------------|---------|
| GET | `/train/model/list` | `module_train:model:query` | `list_models` |
| GET | `/train/model/detail/{model_id}` | `module_train:model:query` | `get_model` |
| POST | `/train/model/create` | `module_train:model:create` | `create_model` |
| POST | `/train/task/create` | `module_train:task:create` | `create_task` |
| GET | `/train/task/list` | `module_train:task:query` | `list_tasks` |
| GET | `/train/task/{task_id}/detail` | `module_train:task:query` | `get_task` |
| POST | `/train/task/{task_id}/stop` | `module_train:task:update` | `stop_task` |
| POST | `/train/eval/create` | `module_train:eval:create` | `create_eval` |
| GET | `/train/eval/list` | `module_train:eval:query` | `list_evals` |

## Key design decisions

- `create_model` auto-increments semantic version (`v1`, `v2`, ...) by querying latest version for same model name.
- `create_task` selects docker image based on framework (`paddlex` → `paddlecloud/paddlex:3.0`, else `ultralytics/ultralytics:latest`).
- `stop_task` delegates to `scheduler.stop_training()` (placeholder for now).
- All endpoints return `SuccessResponse(data=..., msg=...)`.
- Router named `router` for auto-discovery by plugin loader.

## Commit

`6d96140` — `feat(train): add REST API endpoints and service layer`
