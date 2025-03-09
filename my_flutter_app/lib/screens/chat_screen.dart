// /my_flutter_app/lib/screens/chat_screen.dart


import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../services/chat_service.dart';
import '../widgets/chat_widget.dart';

class ChatScreen extends StatelessWidget {
  final String? selectedProjectId;

  const ChatScreen({Key? key, this.selectedProjectId}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    final chatService = Provider.of<ChatService>(context, listen: false);
    if (selectedProjectId != null && chatService.currentProjectId != selectedProjectId) {
      chatService.setProjectId(selectedProjectId!);
    }

    return Expanded(
      flex: 4,
      child: ChatWidget(),
    );
  }
}