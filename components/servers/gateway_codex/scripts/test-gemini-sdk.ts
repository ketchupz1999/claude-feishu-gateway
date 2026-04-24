import { Config, makeFakeConfig } from '@google/gemini-cli-core';

async function test() {
  const config = makeFakeConfig({
    model: 'gemini-2.0-flash',
    cwd: process.cwd(),
  });

  await config.initialize();

  const client = config.geminiClient;
  await client.initialize();

  console.log('Client initialized');

  const events = client.sendMessageStream('Hello, who are you?', new AbortController().signal, 'test_prompt');

  for await (const event of events) {
    if (event.type === 'chunk') {
      const text = event.value.candidates?.[0]?.content?.parts?.[0]?.text;
      if (text) {
        process.stdout.write(text);
      }
    }
  }
  console.log('\nChat finished');
}

test().catch(console.error);
