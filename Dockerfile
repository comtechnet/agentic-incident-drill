FROM node:24-alpine
WORKDIR /app
COPY package.json ./
COPY src ./src
COPY data ./data
USER node
ENV PORT=8070
EXPOSE 8070
CMD ["node", "src/server.js"]
