// nRouter — Java hello world
// Maven: com.openai:openai-java:2.2.0

import com.openai.client.OpenAIClient;
import com.openai.client.okhttp.OpenAIOkHttpClient;
import com.openai.models.*;

public class HelloNRouter {
    public static void main(String[] args) {
        OpenAIClient client = OpenAIOkHttpClient.builder()
                .apiKey(System.getenv("NROUTER_API_KEY"))
                .baseUrl("https://api.nrouter.ai/v1")
                .build();

        ChatCompletion response = client.chat().completions().create(
                ChatCompletionCreateParams.builder()
                        .model("claude-sonnet-4-20250514")
                        .addMessage(ChatCompletionMessageParam.ofUser(
                                ChatCompletionUserMessageParam.builder()
                                        .content("Hello, nRouter!")
                                        .build()
                        ))
                        .build()
        );

        System.out.println(response.choices().get(0).message().content());
    }
}
