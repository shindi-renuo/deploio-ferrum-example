What a beautiful way to manage your schema...


```sql
CREATE TABLE pdf_tasks (
    task_id VARCHAR(255) PRIMARY KEY,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    pdf_url TEXT,
    pdf_file_name VARCHAR(255),
    error TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE
);
```
