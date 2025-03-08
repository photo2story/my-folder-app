// /my_flutter_app/lib/main.dart


import 'package:flutter/material.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:provider/provider.dart';
import 'screens/file_explorer_screen.dart';
import 'services/api_service.dart';
import 'services/file_explorer_service.dart';
import 'package:url_launcher/url_launcher.dart';
import 'widgets/tree_view.dart';
import 'package:my_flutter_app/models/file_node.dart' as model;

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Hive.initFlutter();
  await Hive.openBox('chatBox');
  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => FileExplorerService(apiService: ApiService())),
      ],
      child: const MyApp(),
    ),
  );
}

class MyApp extends StatelessWidget {
  const MyApp({Key? key}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Project Audit Explorer',
      theme: ThemeData(
        primarySwatch: Colors.blue,
        visualDensity: VisualDensity.adaptivePlatformDensity,
      ),
      home: const MainScreen(),
    );
  }
}

class MainScreen extends StatefulWidget {
  const MainScreen({Key? key}) : super(key: key);

  @override
  State<MainScreen> createState() => _MainScreenState();
}

class _MainScreenState extends State<MainScreen> {
  String? _selectedProjectId;
  final _chatController = TextEditingController(); // _chatController 정의
  late FileExplorerService _fileExplorerService;

  @override
  void initState() {
    super.initState();
    _fileExplorerService = Provider.of<FileExplorerService>(context, listen: false);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _fileExplorerService.loadRootDirectory().then((_) {
        print('[DEBUG] Root directory loaded: ${_fileExplorerService.rootNodes?.length} projects');
      }).catchError((e) {
        print('[ERROR] Failed to load root directory: $e');
      });
    });
  }

  void _openFile(String filePath) async {
    if (await canLaunch(filePath)) {
      await launch(filePath);
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Could not open $filePath')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final isMobile = MediaQuery.of(context).size.width < 600;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Project Audit Explorer'),
      ),
      body: isMobile
          ? Column(
              children: [
                Expanded(flex: 2, child: _buildProjectList()),
                Expanded(flex: 4, child: _buildFileExplorer()),
                Expanded(flex: 2, child: _buildChatPanel()),
              ],
            )
          : Row(
              children: [
                Expanded(flex: 2, child: _buildProjectList()),
                Expanded(flex: 4, child: _buildFileExplorer()),
                Expanded(flex: 2, child: _buildChatPanel()),
              ],
            ),
    );
  }

  Widget _buildProjectList() {
    return Consumer<FileExplorerService>(
      builder: (context, service, child) {
        if (service.isLoading) return const Center(child: Text('프로젝트 목록 불러오는 중...'));
        if (service.error != null) return Center(child: Text('Error: ${service.error}'));
        final projects = service.rootNodes ?? [];
        if (projects.isEmpty) return const Center(child: Text('프로젝트가 없습니다'));
        return Container(
          color: Colors.grey[200],
          child: ListView.builder(
            itemCount: projects.length,
            itemBuilder: (context, index) {
              final node = projects[index];
              return ListTile(
                selected: node.path == _selectedProjectId,
                title: Text(node.name),
                onTap: () {
                  setState(() {
                    _selectedProjectId = node.path;
                  });
                  service.loadChildren(node).then((_) {
                    print('[DEBUG] Children loaded for ${node.path}: ${node.children.length} items');
                  }).catchError((e) {
                    print('[ERROR] Failed to load children: $e');
                  });
                },
              );
            },
          ),
        );
      },
    );
  }

  Widget _buildFileExplorer() {
    return Consumer<FileExplorerService>(
      builder: (context, service, child) {
        if (_selectedProjectId == null) {
          return const Center(child: Text('Select a project to view files'));
        }
        final node = service.rootNodes?.firstWhere(
          (n) => n.path == _selectedProjectId,
          orElse: () => model.FileNode(name: '', path: '', isDirectory: true, children: []),
        );
        if (node == null || service.isLoading) {
          return const Center(child: CircularProgressIndicator());
        }
        if (node.children.isEmpty) {
          return const Center(child: Text('No files available'));
        }
        return TreeView(
          nodes: node.children,
          onNodeTap: (node) {
            if (node.path.isNotEmpty && _openFile != null) _openFile!(node.path);
          },
          onNodeExpand: (expandedNode) {
            if (!expandedNode.children.isEmpty) return;
            service.loadChildren(expandedNode).then((_) {
              print('[DEBUG] Expanded node ${expandedNode.path} loaded');
            }).catchError((e) {
              print('[ERROR] Failed to expand node: $e');
            });
          },
        );
      },
    );
  }

  Widget _buildChatPanel() {
    return Container(
      color: Colors.grey[100],
      child: Column(
        children: [
          Expanded(
            child: ValueListenableBuilder(
              valueListenable: Hive.box('chatBox').listenable(),
              builder: (context, Box box, _) {
                final messages = box.get(_selectedProjectId ?? '', defaultValue: <String>[]);
                return ListView.builder(
                  itemCount: messages.length,
                  itemBuilder: (context, index) {
                    return ListTile(
                      title: Text(messages[index]),
                    );
                  },
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
                    controller: _chatController, // _cha -> _chatController로 수정
                    decoration: const InputDecoration(
                      hintText: 'Add a note...',
                      border: OutlineInputBorder(),
                    ),
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.send),
                  onPressed: _selectedProjectId == null
                      ? null
                      : () {
                          if (_chatController.text.isNotEmpty) {
                            final box = Hive.box('chatBox');
                            final messages = List<String>.from(box.get(_selectedProjectId!, defaultValue: <String>[]));
                            messages.add(_chatController.text);
                            box.put(_selectedProjectId!, messages);
                            _chatController.clear();
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

  @override
  void dispose() {
    _chatController.dispose();
    super.dispose();
  }
}