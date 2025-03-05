import 'dart:convert';
import 'dart:io';
import 'package:path/path.dart' as path;
import 'file_explorer_service.dart';

class ApiService {
  static const String baseDir = '../static/results';

  Future<List<Map<String, dynamic>>> fetchProjects() async {
    try {
      print('Fetching projects from local directory');
      final directory = Directory(baseDir);
      if (!directory.existsSync()) {
        print('Directory not found: $baseDir');
        return [];
      }

      final List<Map<String, dynamic>> projects = [];
      final files = directory.listSync().where((f) => f.path.endsWith('.json'));
      
      for (final file in files) {
        try {
          final content = File(file.path).readAsStringSync();
          final data = jsonDecode(content) as Map<String, dynamic>;
          projects.add(data);
        } catch (e) {
          print('Error reading file ${file.path}: $e');
          continue;
        }
      }

      print('Found ${projects.length} projects');
      return projects;
    } catch (e) {
      print('Error fetching projects: $e');
      throw Exception('Failed to load projects: $e');
    }
  }

  Future<List<FileNode>> fetchDirectoryContents(String path) async {
    try {
      print('Fetching directory contents for path: $path');
      final response = await http.get(
        Uri.parse('$baseUrl/api/directory').replace(
          queryParameters: {'path': path},
        ),
      );
      print('Directory contents response status: ${response.statusCode}');
      print('Directory contents response body: ${response.body}');
      
      if (response.statusCode == 200) {
        final List<dynamic> data = jsonDecode(response.body);
        return data.map((json) => FileNode(
          path: json['path'],
          label: json['label'],
          isDirectory: json['isDirectory'],
          lastModified: json['lastModified'] != null
              ? DateTime.parse(json['lastModified'])
              : null,
        )).toList();
      } else {
        throw Exception('Failed to load directory contents: ${response.statusCode}');
      }
    } catch (e) {
      print('Error fetching directory contents: $e');
      throw Exception('Failed to connect to server: $e');
    }
  }

  Future<Map<String, dynamic>> fetchProjectAudit(String projectId) async {
    try {
      final filePath = path.join(baseDir, 'audit_$projectId.json');
      print('Reading audit file: $filePath');

      if (!File(filePath).existsSync()) {
        throw Exception('Audit file not found for project: $projectId');
      }

      final content = File(filePath).readAsStringSync();
      final data = jsonDecode(content) as Map<String, dynamic>;
      print('Loaded audit data for project: $projectId');
      return data;
    } catch (e) {
      print('Error loading audit data: $e');
      throw Exception('Failed to load audit data: $e');
    }
  }
} 