// nRouter — Java hello world
// Maven: ai.nrouter:nrouter-sdk:1.0.0

import ai.nrouter.sdk.NRouter;
import com.openai.client.OpenAIClient;
import com.openai.models.chat.completions.ChatCompletion;
import com.openai.models.chat.completions.ChatCompletionCreateParams;
import com.openai.models.chat.completions.ChatCompletionMessageParam;
import com.openai.models.chat.completions.ChatCompletionUserMessageParam;

public class HelloNRouter {
    public static void main(String[] args) {
        OpenAIClient client = NRouter.create();
        // A Smart Router alias activates its strategy/fallback chain; a
        // concrete model id pins the request to that model.
        String model = System.getenv().getOrDefault(
                "NROUTER_MODEL", "claude-sonnet-4-5-20250929");

        ChatCompletion response = client.chat().completions().create(
                ChatCompletionCreateParams.builder()
                        .model(model)
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
