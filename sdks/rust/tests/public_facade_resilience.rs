use std::io::{Read, Write};
use std::net::TcpListener;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::{Duration, Instant};

fn refusing_gateway() -> (
    String,
    Arc<AtomicUsize>,
    Arc<AtomicBool>,
    thread::JoinHandle<()>,
) {
    let listener = TcpListener::bind("127.0.0.1:0").expect("bind test gateway");
    listener
        .set_nonblocking(true)
        .expect("make test gateway nonblocking");
    let address = listener.local_addr().expect("test gateway address");
    let calls = Arc::new(AtomicUsize::new(0));
    let observed = Arc::clone(&calls);
    let stop = Arc::new(AtomicBool::new(false));
    let stopped = Arc::clone(&stop);
    let handle = thread::spawn(move || {
        let deadline = Instant::now() + Duration::from_secs(10);
        while !stopped.load(Ordering::SeqCst) && Instant::now() < deadline {
            match listener.accept() {
                Ok((mut socket, _)) => {
                    socket
                        .set_read_timeout(Some(Duration::from_secs(1)))
                        .expect("set socket timeout");
                    let mut request = [0_u8; 4096];
                    let _ = socket.read(&mut request);
                    observed.fetch_add(1, Ordering::SeqCst);
                    socket
                        .write_all(
                            b"HTTP/1.1 503 Service Unavailable\r\ncontent-type: application/json\r\ncontent-length: 69\r\nconnection: close\r\n\r\n{\"error\":{\"message\":\"try another deployment\",\"type\":\"gateway_error\"}}",
                        )
                        .expect("write refusal");
                }
                Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                    thread::sleep(Duration::from_millis(10));
                }
                Err(error) => panic!("test gateway accept failed: {error}"),
            }
        }
    });
    (format!("http://{address}/v1"), calls, stop, handle)
}

fn stalling_gateway() -> (String, Arc<AtomicBool>, thread::JoinHandle<()>) {
    let listener = TcpListener::bind("127.0.0.1:0").expect("bind stalling gateway");
    let address = listener.local_addr().expect("stalling gateway address");
    let stop = Arc::new(AtomicBool::new(false));
    let stopped = Arc::clone(&stop);
    let handle = thread::spawn(move || {
        let (mut socket, _) = listener.accept().expect("accept request");
        socket
            .set_read_timeout(Some(Duration::from_secs(1)))
            .expect("set socket timeout");
        let mut request = [0_u8; 4096];
        let _ = socket.read(&mut request);
        socket
            .write_all(
                b"HTTP/1.1 200 OK\r\ncontent-type: application/json\r\ncontent-length: 128\r\nconnection: close\r\n\r\n{",
            )
            .expect("write partial response");
        while !stopped.load(Ordering::SeqCst) {
            thread::sleep(Duration::from_millis(10));
        }
    });
    (format!("http://{address}/v1"), stop, handle)
}

fn chat_request() -> async_openai::types::chat::CreateChatCompletionRequest {
    use async_openai::types::chat::{
        ChatCompletionRequestUserMessageArgs, CreateChatCompletionRequestArgs,
    };
    CreateChatCompletionRequestArgs::default()
        .model("test-model")
        .messages(vec![ChatCompletionRequestUserMessageArgs::default()
            .content("hello")
            .build()
            .expect("user message")
            .into()])
        .build()
        .expect("chat request")
}

#[tokio::test]
async fn public_facade_has_a_deadline_and_does_not_retry_a_billed_request() {
    let (base_url, calls, stop, gateway) = refusing_gateway();
    let client = nrouter::client_with_key_and_base_url("sk-nrouter-test", &base_url)
        .expect("build public client");

    let rendered = format!("{client:?}");
    assert!(
        rendered.contains("read_timeout: 600s"),
        "the public facade installed an unbounded reqwest client: {rendered}"
    );

    let error = client
        .chat()
        .create(chat_request())
        .await
        .expect_err("503 must fail");
    stop.store(true, Ordering::SeqCst);
    gateway.join().expect("test gateway thread");
    assert_eq!(
        calls.load(Ordering::SeqCst),
        1,
        "the SDK retried a gateway-owned failure and would bill the customer twice: {error}"
    );
}

#[tokio::test]
async fn public_facade_cuts_a_post_header_stall_at_its_read_deadline() {
    let (base_url, stop, gateway) = stalling_gateway();
    let transport = reqwest::Client::builder()
        .connect_timeout(Duration::from_secs(1))
        .read_timeout(Duration::from_millis(75))
        .build()
        .expect("short-deadline transport");
    let client =
        nrouter::client_with_key_base_url_and_http_client("sk-nrouter-test", &base_url, transport)
            .expect("build public client");

    let result =
        tokio::time::timeout(Duration::from_secs(2), client.chat().create(chat_request())).await;
    stop.store(true, Ordering::SeqCst);
    gateway.join().expect("stalling gateway thread");
    assert!(
        result.is_ok(),
        "the executing request ignored its read deadline"
    );
    assert!(
        result.expect("outer test deadline").is_err(),
        "a truncated JSON response cannot succeed"
    );
}
