// /my_flutter_app/lib/widgets/chat_widge.dart


import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import '../services/chat_service.dart';

class ChatWidget extends StatefulWidget {
  @override
  _ChatWidgetState createState() => _ChatWidgetState();
}

class _ChatWidgetState extends State<ChatWidget> {
  final TextEditingController _chatController = TextEditingController();
  final ScrollController _scrollController = ScrollController();

  @override
  void dispose() {
    _chatController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final chatService = Provider.of<ChatService>(context);

    return Container(
      color: Colors.grey[100],
      child: Column(
        children: [
          Expanded(
            child: ListView.builder(
              controller: _scrollController,
              itemCount: chatService.messages.length,
              itemBuilder: (context, index) {
                final message = chatService.messages[index];
                return Card(
                  margin: const EdgeInsets.symmetric(horizontal: 8.0, vertical: 4.0),
                  child: Padding(
                    padding: const EdgeInsets.all(12.0),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        // 마크다운으로 메시지 표시
                        _buildMarkdownWidget(message),
                        const SizedBox(height: 8),
                        Text(
                          DateTime.now().toString().substring(0, 19),
                          style: const TextStyle(fontSize: 10, color: Colors.grey),
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(8.0),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _chatController,
                    decoration: const InputDecoration(
                      hintText: '메모 추가...',
                      border: OutlineInputBorder(),
                    ),
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.send),
                  onPressed: () {
                    if (_chatController.text.isNotEmpty) {
                      chatService.addMessage(_chatController.text);
                      _chatController.clear();
                      // 메시지 추가 후 스크롤을 아래로 이동
                      Future.delayed(Duration(milliseconds: 100), () {
                        if (_scrollController.hasClients) {
                          _scrollController.animateTo(
                            _scrollController.position.maxScrollExtent,
                            duration: Duration(milliseconds: 300),
                            curve: Curves.easeOut,
                          );
                        }
                      });
                    }
                  },
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildMarkdownWidget(String message) {
    try {
      return MarkdownBody(
        data: message,
        selectable: true,
        styleSheet: MarkdownStyleSheet.fromTheme(Theme.of(context)).copyWith(
          p: TextStyle(fontFamily: 'NotoSansKR', fontSize: 14, height: 1.5),
          h1: TextStyle(fontFamily: 'NotoSansKR', fontSize: 20, fontWeight: FontWeight.bold, height: 1.5),
          h2: TextStyle(fontFamily: 'NotoSansKR', fontSize: 18, fontWeight: FontWeight.bold, height: 1.5),
          h3: TextStyle(fontFamily: 'NotoSansKR', fontSize: 16, fontWeight: FontWeight.bold, height: 1.5),
          strong: TextStyle(fontFamily: 'NotoSansKR', fontWeight: FontWeight.bold),
          em: TextStyle(fontFamily: 'NotoSansKR', fontStyle: FontStyle.italic),
        ),
      );
    } catch (e) {
      // 마크다운 패키지가 없는 경우 일반 텍스트로 표시
      return SelectableText(
        message,
        style: const TextStyle(
          fontFamily: 'NotoSansKR', 
          fontSize: 14,
          height: 1.5,
        ),
      );
    }
  }
}