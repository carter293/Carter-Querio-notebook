import { defineConfig } from '@hey-api/openapi-ts';

export default defineConfig({
  input: 'http://localhost:8000/openapi.json',
  output: {
    path: 'src/client',
    format: 'prettier',
  },
  // Fetch client is the default and is bundled with @hey-api/openapi-ts
  // No need to specify client option unless using a different client
});

