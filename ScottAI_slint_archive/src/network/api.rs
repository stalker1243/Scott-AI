use serde::Deserialize;
use std::time::Duration;

#[derive(Debug, thiserror::Error)]
pub enum ApiError {
    #[error("сеть: {0}")]
    Network(#[from] reqwest::Error),
    #[error("backend вернул ошибку: {0}")]
    Backend(String),
}

#[derive(Debug, Deserialize)]
struct HealthResponse {
    #[allow(dead_code)]
    status: String,
}

#[derive(Debug, Deserialize)]
struct AskResponse {
    success: bool,
    #[serde(default)]
    error: Option<String>,
    #[serde(default)]
    data: Option<AskData>,
}

#[derive(Debug, Deserialize)]
struct AskData {
    #[serde(default)]
    answer: String,
}

/// Тонкий HTTP-клиент к backend Scott AI (FastAPI, см. backend/main.py).
/// Методы соответствуют реально существующим REST-эндпоинтам.
#[derive(Clone)]
pub struct BackendClient {
    http: reqwest::Client,
    base_url: String,
}

impl BackendClient {
    pub fn new(base_url: impl Into<String>) -> Self {
        let http = reqwest::Client::builder()
            .timeout(Duration::from_secs(20))
            .build()
            .expect("не удалось создать HTTP-клиент");

        Self {
            http,
            base_url: base_url.into().trim_end_matches('/').to_string(),
        }
    }

    #[allow(dead_code)]
    pub fn base_url(&self) -> &str {
        &self.base_url
    }

    /// GET /health — используется для индикатора online/offline.
    pub async fn health(&self) -> Result<(), ApiError> {
        let resp = self
            .http
            .get(format!("{}/health", self.base_url))
            .send()
            .await?
            .error_for_status()?;

        let _: HealthResponse = resp.json().await?;
        Ok(())
    }

    /// POST /ask — задать вопрос/команду Scott и получить текстовый ответ.
    pub async fn ask(&self, question: &str) -> Result<String, ApiError> {
        let resp = self
            .http
            .post(format!("{}/ask", self.base_url))
            .json(&serde_json::json!({ "question": question }))
            .send()
            .await?;

        let parsed: AskResponse = resp.json().await?;

        if !parsed.success {
            return Err(ApiError::Backend(
                parsed.error.unwrap_or_else(|| "неизвестная ошибка".to_string()),
            ));
        }

        Ok(parsed.data.map(|d| d.answer).unwrap_or_default())
    }
}
