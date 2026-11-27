FROM node:20-alpine

WORKDIR /workspace/apps/web

COPY apps/web/package.json /workspace/apps/web/package.json
RUN npm install

COPY apps/web /workspace/apps/web

ARG NEXT_PUBLIC_API_BASE_URL
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL:-http://localhost:8000}
RUN npm run build

CMD ["npm", "run", "start"]
