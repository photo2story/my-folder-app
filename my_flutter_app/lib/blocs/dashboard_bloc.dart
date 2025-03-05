import 'package:bloc/bloc.dart';
import 'package:equatable/equatable.dart';
import '../models/project_model.dart';
import '../services/api_service.dart';

// Events
abstract class DashboardEvent extends Equatable {
  const DashboardEvent();

  @override
  List<Object> get props => [];
}

class LoadDashboardData extends DashboardEvent {}

// States
abstract class DashboardState extends Equatable {
  const DashboardState();

  @override
  List<Object> get props => [];
}

class DashboardInitial extends DashboardState {}

class DashboardLoading extends DashboardState {}

class DashboardLoaded extends DashboardState {
  final List<ProjectModel> projects;

  const DashboardLoaded(this.projects);

  @override
  List<Object> get props => [projects];
}

class DashboardError extends DashboardState {
  final String message;

  const DashboardError(this.message);

  @override
  List<Object> get props => [message];
}

// Bloc
class DashboardBloc extends Bloc<DashboardEvent, DashboardState> {
  final ApiService apiService;

  DashboardBloc({required this.apiService}) : super(DashboardInitial()) {
    on<LoadDashboardData>(_onLoadDashboardData);
  }

  Future<void> _onLoadDashboardData(
    LoadDashboardData event,
    Emitter<DashboardState> emit,
  ) async {
    emit(DashboardLoading());
    try {
      final projects = await _fetchProjects();
      emit(DashboardLoaded(projects));
    } catch (e) {
      emit(DashboardError('데이터 로드 실패: $e'));
    }
  }

  Future<List<ProjectModel>> _fetchProjects() async {
    try {
      final response = await apiService.fetchProjects();
      return response.map((json) => ProjectModel.fromJson(json)).toList();
    } catch (e) {
      throw Exception('프로젝트 데이터 로드 실패: $e');
    }
  }
} 